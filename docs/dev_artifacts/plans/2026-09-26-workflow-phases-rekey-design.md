---
id: 2026-09-26-workflow-phases-rekey-design
type: plan
title: "Re-key `workflow_phases` per entity: design (Phase R, step R1)"
status: done
---
# Re-key `workflow_phases` per entity: design (Phase R, step R1)

- **Status:** R1 draft, revised once for calvin's ledger (its section holds the author's answers), then once for R3's independent verification (premortem, code verification, live-copy rehearsal, blast radius). That R3 revision is the plan's one revision (plan:313); the last section records it, disposition by disposition.
- **Date:** 2026-09-26.
- **What it targets:** Phase 1 as landed on develop `c1bbfae0` (its code equals `ddc299a0`):
  - 1A (W2.1–W2.7);
  - 1B's W1 as executed, with its execution notes;
  - 1C's brainstorm registration, scoped to the session's workspace, which skips a type_id another workspace holds and names it in the warnings. RK2 removes that skip (section 6.1).
- **Anchors** (re-derived by the R3 revision):
  - **Code:** file:line citations were taken at `4a6373f0` (1A's branch). Those that moved by develop `c1bbfae0` are listed in `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/logs/anchors-moved.txt`, and this revision applies each row to the lines it names. The same line map (both commits' text, lines matched by content) re-anchored the moved citations that list leaves out, such as the bare line numbers of 6.3. So every file:line citation in sections 1–15 is at `c1bbfae0`, except the few that name code Phase 1 deleted, which say `4a6373f0`.
  - **Figures** keep the commit they were measured at, which the text names.
  - **The plan and design rev 2.1:** cited at develop `c1bbfae0`. Plan citations follow `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/plan-anchor-map.txt`; design rev 2.1's were re-derived the same way.
  - **Inventory row ids** (for example `schema-32`) point into the inventory, whose own lines are at `77f06efb`.
  - **The calvin ledger** keeps the line numbers calvin read.
  - **Re-anchoring:** each RK task re-verifies its rows' anchors by symbol on its own branch before editing, as the plan's anchor rule says (plan:72), and records old → new in its task report (open question 25).
- **Inputs:**
  - the plan, `docs/dev_artifacts/plans/2026-09-25-release-c-followups-implementation-plan.md` ("plan:", lines at develop `c1bbfae0`), section "Phase R";
  - design rev 2.1, `docs/dev_artifacts/plans/2026-09-25-release-c-followups-design.md` ("design:", lines at develop `c1bbfae0`);
  - the playbook, `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-playbook.md` (sandbox copy `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/workflow-phases-rekey-playbook.md`), cited "playbook §N". Its tasks carry this design's work units (section 15);
  - R3's findings and their dispositions: `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/` (premortem, build, rehearsal and blast reports) and `r3/revision/dispositions.md`, whose row ids the last section cites;
  - the inventory: `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-inventory.md`, its home (plan:277), copied there with this design on 2026-09-29 from `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/inventory.md`. Its rows are in `inventory.json` beside the sandbox copy (369 rows, cited by row id, for example `schema-32`).
- **This design's own evidence** stays in the main checkout's gitignored sandbox, as the plan's evidence rule says (plan:50-51), under `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/`:
  - `census/census.py` → `census/census-live.json`: the live registry, read with `immutable=1`;
  - `census/shared.py`, `census/events_twins.py`: the seven shared type_ids;
  - `proto/rekey_migration.py`: the migration of section 4, as a prototype;
  - `proto/run_proto.py` → `proto/proto-results.json`: that migration applied to four files, with every check in sections 4, 5 and 13;
  - `scan/*.py`: AST counts of SQL statements and API calls over the `4a6373f0` export;
  - `merge_probe/`: `scripts/migrate_db.py merge-entities` run on today's schema;
  - `calvin/*.py` → `calvin/*.out`: the probes behind the author's answers to calvin's ledger (its section), and `calvin/design-before-calvin.md`, this design as calvin read it.
- **Live registry:** `1790286038 4083712`, sha256 prefix `2814bb4434e8faa0`, before and after every run. Never opened except with `immutable=1`; every experiment ran on a copy made with the prescribed `s.backup(d)` command.
- **Names used below:**
  - **fresh file:** `EntityDatabase(path)` on a new path; v1 generation, `schema_version` 25 today.
  - **live file:** `~/.claude/pd/entities/entities.db`; v2 generation, `schema_version` 7.
  - **the naming rule:** section 6.1. **row view:** section 6.2.
  - **Row classes** (section 5.1) and **event classes** (section 3.3) have descriptive names, such as "matched" or "sole-holder". W1–W5 always mean design rev 2.1's workstreams, and P0–P2 the plan's priorities.
  - **RK1–RK6:** the work units of section 15. **R4-A … R4-I, R4-C0, R4-F1 … R4-F4:** the playbook's tasks, which section 15 maps to them.
  - **Q1–Q7:** the user's questions (section 9).
  - **today:** 2026-09-26: the code on develop `c1bbfae0` (Phase 1 landed) and the live registry at fingerprint `1790286038 4083712`. A figure measured on the earlier `4a6373f0` says so.
  - **dark:** shipped code that no production path reaches.
    - **The dark v2 core** is `schema_v2._CORE_DDL`: its module "Ships dark" (schema_v2.py:1-8), and its `entities.type_id` is "NOT unique (FR-4)" (schema_v2.py:64). Production files keep `UNIQUE(workspace_uuid, type_id)`.
    - **FR-4** is feature 118's requirement "No uniqueness constraint on any human-readable field" (`docs/dev_artifacts/workitems/118-uuidv7-identity-migration/spec.md:9`).
    - **The dark engine paths** are engines-13 to -16, which only tests reach (inventory `reached_from`).
  - **Release C items:** C8 (readers take `kind` from `entities.kind`), C22 (recreate the live remainder, `scripts/c22_recreate_live_remainder.py`) and C23 (old builds fail loudly, not write quietly). They are defined in `docs/dev_artifacts/plans/2026-09-20-display-id-ownership-implementation.md` (:328-334, :412, :425).
  - **5D:** the five-phase sequence `FiveDBackend` runs for L1, L2 and L4 entities (entity_engine.py:9, :106). No live entity has such a kind.

## 1. Problem and bar

### 1.1 What problem 1 needs

Two halves, both named by design rev 2.1's root cause 3 (design:116-122) and by I1's correction 1. That correction says keying `workflow_phases` per workspace "is necessary but not enough", because the "entity not found" answers come from unscoped `get_entity(type_id)` calls (`agent_sandbox/2026-09-25/release-c-followups/I1/report.md:15`, upheld by `I1-verify/verdict.md:13`). The plan restates it (plan:294):

1. **The row key.** `workflow_phases` is keyed by `type_id TEXT PRIMARY KEY`, while an entity is unique per `(workspace_uuid, type_id)`.
   - **Where it comes from:** migration 3, `_create_workflow_phases_table` (database.py:378-470). Migration 8 dropped the table's foreign key to entities when entities became unique per project (:1200-1270, inventory 2.2). Fresh and live files carry the identical table text (inventory 2.6).
   - **One row per type_id, not per entity:** live, 7 type_ids are held by more than one workspace.
     - **Five have one row each,** pedantic-drip's. Their five terry_agent namesakes can never get one, because the primary key is taken (census `wp_shared_typeid_rows`).
     - **Two have none:** `feature:035-slim-watchdog-self-mgmt` (both holders archived) and `project:P001` (three holders; projects get no rows).
   - **The copies drift:** `workspace_uuid` and `uuid` are unenforced copies of the entity's identity.
     - `backfill_project_ids` (database.py:8818) and `claim_unknown_entities` (:9130) re-attribute entities without touching them (inventory schema-47, schema-48, MCPE-3).
     - 8 live rows have a NULL `uuid` (census).
   - **Three unscoped settlements** of a shared type_id (design:118-121):
     - `get_entity` answers None;
     - `wp_autofill_workspace_uuid` (database.py:2062) takes the smallest workspace;
     - `create_workflow_phase`'s old fallback took the lowest rowid (W2.1 already refuses it at `4a6373f0`).
2. **The unscoped reads.** Inventory section 6:
   - **The 39 `get_entity` lines** hold 36 type_id reads; 34 survive Phase 1 (inventory 6.1).
   - **40 rows are always unscoped** (inventory 6.2) and **15 are unscoped on some paths** (inventory 6.3).
   - **Seven lookups settle a shared type_id five different ways** (inventory 6.4, at `77f06efb`): they raise "Ambiguous", answer None, take the lowest rowid (three of them), answer only when the namesakes agree, or take the smallest workspace. At `4a6373f0`, W2.1 makes `create_workflow_phase`'s lookup refuse, so two still take the lowest rowid. For example, `resolve_ref`'s exact match does, with no error (database.py:7236-7239).
   - **Why they wait for the re-key:** design rev 2.1 deferred scoping them "only after the re-key, or today's refusals become cross-workspace writes" (design:389). A read scoped to workspace A that finds A's entity would then write the type_id-keyed row that belongs to B. Once rows are keyed by entity, that write cannot happen.
   - **Why the re-key needs them in the same round:**
     - **Left unscoped,** `get_entity` still answers None for both namesakes, so the second workspace's feature is "not found" even with its own row (I1's correction 1).
     - **And `resolve_ref`'s unscoped exact match** takes the lowest rowid: once writes go by the resolved entity's uuid, a caller in B could write A's row.
     - **So:** scoping without the re-key is unsafe, and the re-key without scoping leaves problem 1 open. The two halves land together.
3. **`phase_events` has no entity key at all.**
   - **Its entity:** the `type_id` text. **Its workspace:** the legacy label `project_id`, which names the holder's workspace for only 1088 of the 1469 live rows (census `pe_strict_label_map`).
   - **Why it matters:** readers read every namesake's events. For example, `get_mini_spec` (workflow_state_server.py:2328-2365), which decides the express lane.

### 1.2 The bar for "solved"

Observable facts, each with the check that shows it:

1. **Per-entity rows.** Two workspaces holding `feature:X` each have their own row, and a write through one never changes the other's.
   - Test: `test_two_namesakes_two_rows_and_no_cross_write` (section 10).
   - Live copy: after the migration, a second row for terry_agent's `feature:002-assessed-mode-pipeline-fix` inserts (prototype `second_row_same_type_id` = 2).
2. **No type_id-only access.**
   - Every library call that names an entity by type_id carries a workspace, or raises.
   - No SQL in the scan roots keys either table by type_id alone, outside the guard's declared allow-list (section 11): the historical migrations, and at most two named functions while they last.
   - Neither table has a type_id key in the schema.
   - Checks: the refusal tests (section 6.3) and the guard test (section 11).
3. **Per-entity event streams.** Reading one namesake's phase events never returns the other's. Test: `test_mini_spec_of_a_is_invisible_to_b` (section 10, criterion 4).
4. **Identity changes need no cascade.** A rename, a re-attribution, a reparenting, an archive and a soft delete each leave the row and the events attached to their entity. Checks: the criterion-2 tests (section 10).
5. **The live file migrates with nothing lost.**
   - All 529 rows keep their state: the six state columns, and the workspace and type_id they belong to, now read through the key (Q-rows-kept). Every stored `uuid` becomes the key (Q-stale-uuid).
   - 1444 of the 1469 events gain their entity; 25 stay unattributed, by rule.
   - An audit row records the counts.
   - Check: the R3 rehearsal (section 13.5), which repeats the prototype on a fresh copy.
6. **W3.1–W3.3's user-visible checks pass on the new key:** one card per row, working uuid links, lineage by uuid, and the Entities page per namesake (section 7).

### 1.3 What a pd user sees, without the re-key and with it

- **Without it, after Phase 1:** in a workspace whose feature shares its type_id with another workspace's entity, activating that feature answers `feature_not_found`. The unscoped `get_entity` answers None for a shared type_id (feature_lifecycle.py:593-595).
  - **Scoping that read alone is not enough:** the row check that follows finds the other workspace's row by type_id and seeds none (feature_lifecycle.py:604-610). The step-5 projection of every later transition then updates the row by type_id alone (database.py:9790), which is the other workspace's.
  - **Reads leak too:** `get_mini_spec` (workflow_state_server.py:2328-2365) reads both namesakes' events, so one workspace's mini-spec could steer the other's express lane.
- **Who hits it today:** terry_agent's five namesakes (5.3), which can never get a row, and any type_id two workspaces come to hold.
  - **Since 1C (`ddc299a0`),** session start skips a brainstorm file whose type_id only another workspace holds, and names it in the warnings (entity_status.py:160-167). RK2 removes the skip (section 6.1).
- **Once the bar in 1.2 is met:** each namesake has its own row and its own event stream, and the second workspace's activation succeeds. The board shows one card per row, and each card links to its owner's entity (section 7).

## 2. Key choice

### 2.1 The options

- **A. The entity uuid is the key; `type_id` and `workspace_uuid` are dropped** and derived by a join to `entities`.
- **B. The entity uuid is the key; `type_id` and `workspace_uuid` are kept as copies,** enforced either:
  - by a composite foreign key with `ON UPDATE CASCADE`, which needs a new UNIQUE index on `entities(uuid, workspace_uuid, type_id)`; or
  - by triggers on `entities`.
- **C. The composite key `(workspace_uuid, type_id)`,** with `uuid` kept as a copy.

### 2.2 Scored against the seven future-proof criteria (plan:279-290)

| Criterion | A | B | C |
|---|---|---|---|
| 1. One row per entity, schema-enforced | **Yes:** PRIMARY KEY `entity_uuid` | **Yes** | **Only while** entities stay unique per `(workspace, type_id)`. The dark v2 core declares `type_id` not unique (schema_v2.py:64, FR-4); C would break if that ever reached a live file, which nothing schedules. |
| 2. Survives identity change | **Yes, with no cascade:** the key is the one column `enforce_immutable_uuid` protects. A rename, re-attribution, reparent, archive, soft delete or shared type_id touches no row. | **Needs cascades** on rename and re-attribution. A foreign-key cascade runs only on connections with `PRAGMA foreign_keys = ON`. A trigger cascade would run inside the drop-and-recreate of `enforce_immutable_workspace_uuid` that every re-attributing writer does (`update_entity`, database.py:8762-8812; `backfill_project_ids`, :8935; `claim_unknown_entities`, :9221): each writer must keep both guards straight, and a failure between the drop and the recreate leaves one missing (hence `update_entity`'s best-effort recreate, :8802-8812). | **The key itself moves** on rename and re-attribution; `enforce_immutable_wp_type_id` must go, and the cascade is again per-connection. |
| 3. No copy drifts silently | **Yes:** no copy exists. | **Conditional:** only on connections with foreign keys on, or with trigger discipline. | **No:** the `uuid` copy drifts unless it is also foreign-keyed. |
| 4. No path reaches another workspace's row by type_id | **Mostly structural:** SQL cannot key the table by `type_id`, since the column is gone. The residue, a join through `entities` filtered by type_id alone, needs the same guard B and C rely on for every access (section 11). | **Discipline only:** `WHERE type_id = ?` stays legal SQL and returns up to N rows; only the guard catches it. | **Discipline only:** same as B. |
| 5. One target schema, resumable copy-rename | **Equal:** one copy-rename each. | **Equal** | **Equal** |
| 6. Fits the v2 direction | **Yes:** the same key as `events.entity_uuid` and all three views. On the migrated live copy, every row joins `entity_phase_status` one-to-one by entity uuid (529 of 529). | **Partly:** fits, but keeps a type_id path readers can go on using. | **No:** keyed by a name the v2 core says is not unique. |
| 7. Consistent with rev 2.1 | **Yes,** with W3.1–W3.3 restated (section 7) | **Yes,** restated | **Closest** to W3.1's literal join text |

### 2.3 Cost

Re-derived at `4a6373f0` by `scan/wp_sql_costs.py`. A statement is an AST string literal that starts with SQL and names `workflow_phases`:

- **Runtime production code:** 27 statements in 9 files (16 SELECT, 5 UPDATE, 4 INSERT, 2 DELETE).
  - 25 name `type_id`; 20 key by it (in a `WHERE` or `ON`).
- **Tests:** 118 statements (58 INSERT, 47 SELECT, 7 hand-written CREATE, 5 DELETE, 1 UPDATE).
  - 109 name `type_id`; 44 key by it.
  - Of the 58 INSERTs, 20 name `workspace_uuid` and 2 name `uuid`.
- **Historical migrations:** 40 statements. They stay as written under every option.

What each option must change:

| | A | B | C |
|---|---|---|---|
| Runtime statements | 25: every one that names `type_id` | about 21: the 20 type_id keys, which criterion 4 forces scoped anyway, and 1 INSERT without `uuid` | about 21: the same 20, and 1 INSERT without the workspace |
| Test statements | about 109 | about 56: INSERTs without `uuid` | about 38: INSERTs without the workspace |

- **What A pays beyond B:** about 53 test statements, nearly all single-workspace assertions such as `SELECT workflow_phase FROM workflow_phases WHERE type_id = ?`. Each becomes a join or an API call; the change is mechanical.
- **What every option pays:** the naming rule's API churn: about 1,800 test call sites and about 115 production calls (6.4, measured at `ddc299a0`), against the key choice's difference of about 53 test statements.

### 2.4 Choice: A

- **Structural where it can be:** A is the only option where criterion 3 holds by the schema's shape, and the one where criterion 4 leans least on discipline. There is no copy to drift and no `type_id` column to key by; only a join through `entities` filtered by type_id alone still needs the guard. B and C hold criterion 3 only while every connection has foreign keys on, and criterion 4 only while every author remembers the workspace predicate on every access.
- **It is the v2 key:** `events` and all three views are keyed by entity uuid. Under A, retiring `workflow_phases` means swapping the table for a view with the same key (criterion 6).
- **It survives FR-4:** if `entities.type_id` ever stops being unique per workspace (schema_v2.py:64), A needs no change; C collapses. Nothing schedules that, and the choice does not rest on it: the other reasons hold either way.
- **The price is counted and mechanical:** about 53 extra test statements. The rest of the churn comes from the naming rule, which all three options need.
- **The column name:** `entity_uuid`, the name `events`, `entity_tags`, `entity_okr_alignment` and the views use. It is also the key rev 2.1's W3.1 planned to expose in list results (design:349), which Phase R now delivers: at develop `c1bbfae0`, `list_workflow_phases` selects none (database.py:10455-10461).
- **The table's `uuid` column goes.** On the live file every non-NULL value equals its matched entity's uuid (521 of 521, Q-stale-uuid), but nothing enforces that, which is why the stale-uuid class exists (5.1).
- **What would force another re-key:** only a change of the key itself, the entity uuid.
  - **In place:** `enforce_immutable_uuid` forbids it.
  - **By a rebuild:** `rebuild_tool`'s v1→v2 rebuild is the one path that re-mints uuids, and it maps both tables' keys through its old-to-new map (section 14). A workflow row it forgot to map would name no entity in the new file, which `wp_reject_unknown_entity` refuses at insert. An event's foreign key refuses it on a connection with foreign keys on, and `PRAGMA foreign_key_check(phase_events)` reports it otherwise; R2 adds that check to the rebuild's verification.
  - **Retiring `workflow_phases`** into the v2 events keeps the key (criterion 6).

## 3. `phase_events`

### 3.1 Ruling: it gains the entity key this round

- **Criterion 4, extended by this design:** the plan's criterion 4 names `workflow_phases` (plan:283) and leaves `phase_events` to this design (plan:293). A phase event is part of the same entity's workflow, and reading another workspace's events is the same hazard, so the guard flags `phase_events` accesses keyed by type_id alone too (section 11). With no reliable workspace column, the only per-entity key is the entity uuid.
- **Re-keying `workflow_phases` alone opens a hazard:**
  - `get_mini_spec` (workflow_state_server.py:2328-2365) and `_check_artifact_completeness` (:1316, query at :1348) read every namesake's events.
  - Once two workspaces run `feature:X`, which the re-key makes possible, A's `mini_spec` event would put B's feature on the express lane.
- **`project_id` cannot serve as the key:**
  - it names the holder's workspace for 1088 of 1469 rows;
  - 7 of the 21 workspaces have no legacy id;
  - re-attribution never rewrites it (inventory schema-19; census).
- **The cost is small:**
  - one `ALTER TABLE ... ADD COLUMN` and two UPDATEs;
  - the readers: 7 `query_phase_events` calls and 1 `query_phase_events_bulk` call in workflow_state_server.py, plus rebuild_tool and pd_state_diff;
  - the writers: none of the 10 production `append_phase_event` call sites changes for the column, since each already passes a `workspace_uuid` argument (entity_server.py:981; workflow_state_server.py:1238, :1247, :1544, :2316, :2862; database.py:7768, :7931, :8709; dependencies.py:191). The workflow server's is `_workspace_uuid or None`, which W4.1's `_require_workspace()` sets on every write tool. Tests: 55 calls pass neither `workspace_uuid` nor `entity_uuid` (`calvin/churn_gaps.out`), outside 6.4's count.

### 3.2 Shape

- **New column:** `entity_uuid TEXT REFERENCES entities(uuid)`.
  - **Nullable:** for unattributed history only.
  - **Required on new live rows:** a trigger refuses a `source = 'live'` row without it (section 4.2).
- **`type_id` and `project_id` stay, as write-time labels:**
  - **`type_id`:** the entity's type_id when the event was written.
  - **`project_id`:** the legacy label its writer passed, stored as passed. Most writers pass the entity's workspace's legacy id, or `'__unknown__'` for the 7 workspaces with none (`_resolve_project_id`, workflow_state_server.py:875-898; an entity dict's `project_id` is `w.project_id_legacy`, database.py:8236), or, since 1B, the workspace's uuid for a workspace with no legacy id, as the cascade writer does (dependencies.py:193). `issue_spawn` passes its own server's label, even for a parent in another workspace (entity_server.py:981-985). So the label names the holder's workspace for only 1088 of 1469 live rows (1.1).
  - **What they are for:** the only identity of the 25 unattributed rows (3.3); the evidence the label-decided class uses, and a later repair would; and display in returned rows.
  - **Who reads them after the re-key:** no production code filters or joins on either. The one reader that maps a label to a workspace today, `rebuild_tool`'s event copy (rebuild_tool.py:1015-1072), maps `entity_uuid` instead (section 14).
  - **What `query_phase_events` returns:** each row's `type_id` key is this write-time label, not the entity's current type_id; the two differ after a rename. So no production code may compare it with an entity's current type_id, which RK5's guard checks (section 11, rule 6).
  - **What dropping them would lose:** the label-decided evidence for history. Dropping a column would also need a copy-rename of `phase_events`, which this round avoids (4.2).
  - **Never read as keys:** the guard enforces it (section 11).
  - **Not copies in criterion 3's sense:** the table is a history whose labels are never rewritten, so a label records the past; it does not claim the entity's current identity.
    - **The one update this design allows** sets a NULL `entity_uuid` once: the migration's attribution, and a later explicit repair. `enforce_immutable_pe_entity_uuid` enforces that.
    - **The v2 cutover's one-off pre-pass** that rewrote `phase` values (SCR-11) has already run (section 14).

### 3.3 Classes of old rows

Counts from the live census, re-derived; the rules were applied to a live copy by the prototype.

| Class | Rule | Live rows | Evidence |
|---|---|---|---|
| **sole-holder** | the type_id is held by exactly one entity, whatever the label → that entity | 1436 | 356 of them carry a label naming another workspace or none (`__unknown__` 272, `721cb90c8607` 71, `e8bdba5f147b` 13). The type_id decides, since only one entity anywhere holds it. None of the 74 type_ids behind those 356 was held under another name in any of the 19 registry backups under `~/.claude/pd/entities/` (oldest 2026-03-23). Their uuids differ only across the 2026-07-25 cutover, which re-minted every uuid (`calvin/p1_holder_history.out`). No type_id has two `entity_created` events. An event older than the oldest backup can't be checked this way. |
| **label-decided** | held by several entities, and the label names one holder's workspace, by legacy id or uuid (never `'__unknown__'`) → that holder | 8 | `entity_status_changed` rows, one each for the two brainstorms, features 002–004 and `project:P001`, and two for feature 035 (one per namesake, each under its own workspace's label) |
| **undecided** | held by several entities, and the label names none of them → unattributed (NULL) | 13 | features 002 (5) and 004 (8): `started`/`completed`, `source='backfill'`, label `__unknown__` |
| **no-holder** | held by no entity → unattributed (NULL) | 12 | `entity_created` backfill rows of `backlog:001`–`004` and `backlog:052`–`059`, type_ids renumbered away |

- **Totals:** 1469 rows; 1444 attributed (prototype `pe_attributed`); 0 attributed to an entity with another type_id.
- **Why the undecided class stays unattributed:**
  - **No stored fact decides:** the label is `__unknown__`.
  - **Timestamps don't decide either:** backfilled events routinely predate their own entity's `created_at`. On the live copy, 203 sole-holder events (105 `started`, 98 `completed`, all `source='backfill'`) are more than a second, and up to 68 days, older than their only holder's `created_at` (compared with `julianday`). So "a holder created after the event cannot own it" eliminates no one.
  - **The v2 cutover made the same call:** neither namesake has pipeline events in `events` (census `events_twins.py`). `rebuild_tool` mapped events only by (label → workspace, type_id) (rebuild_tool.py:1019-1072).
  - **The row they would join is itself in doubt:** the artifacts of all five pedantic-drip namesakes exist only in `/Users/terry_agent/docs` (section 5.3).
- **What unattributed rows are afterwards:**
  - kept verbatim, as history;
  - returned by no API that names an entity; `query_phase_events()` with neither an entity nor a workspace (the analytics "all workspaces" view) still lists them;
  - repairable once: a later, explicit repair may set their `entity_uuid`, since the immutability trigger allows NULL → value.

## 4. Target schema

### 4.1 One target for both files

- **One function** serves both chains, following the dual-chain pattern v2 steps 2–7 use (database.py:6481-6517):
  - `V2_MIGRATIONS[8] = _v2_migration_8_rekey_workflow_phases`;
  - `MIGRATIONS[26] = _v2_migration_8_rekey_workflow_phases`, assigned beside `MIGRATIONS[22..25]` (:6496-6499);
  - `schema_v2.V2_SCHEMA_VERSION = 8` (schema_v2.py:31). The import-time assert at database.py:6506 fails if the two move apart.
- **Versions:** a fresh file goes from 25 to 26; the live file from 7 to 8. A staging file built by `rebuild_tool.build_staging_database` reaches v2/8 through both chains (prototype `verify_staging_v2`).
- **Forward-only:** no `MIGRATIONS_DOWN` entry, so `_migrate_down` raises `NotImplementedError` for 26, as it does for 25. Rollback is by restore (section 13.4).

### 4.2 Exact DDL of the target

`workflow_phases`, created as `workflow_phases_new` and renamed. The CHECK lists have the same allowed values as the live DDL (compared as sets by `test_fresh_and_staging_shapes_identical`), which is identical in fresh files (inventory 2.2):

```sql
CREATE TABLE workflow_phases (
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
```

- **No `ON DELETE` clause,** like `events.entity_uuid`:
  - a hard delete of an entity that has a row fails loudly on a connection with foreign keys on, which every `EntityDatabase` connection is (`_set_pragmas`, database.py:11075; prototype `guard_hard_delete_entity_with_row`);
  - so does `DROP TABLE entities` with foreign keys on (probed on the class fixture). That protects against a future copy-rename of `entities` run with foreign keys on, which `ON DELETE CASCADE` would turn into a silent wipe of every row;
  - soft delete, the only delete (`delete_entity`, database.py:8977), keeps the row;
  - **what remains:** a raw-SQL hard delete on a connection with foreign keys off (the `sqlite3` shell's default) can still leave a row whose entity is gone. No pd code does that: `delete_entity` soft-deletes (`UPDATE entities SET is_deleted = 1 … WHERE uuid = ?`, database.py:9094). The doctor reports such a row (section 14); nothing tolerates it.
- **`wp_reject_unknown_entity`** keeps the one property `wp_reject_orphaned_insert` had that the foreign key lacks: it refuses whatever the connection's `PRAGMA foreign_keys`.
- **Not this round's:** the `ready` gap in the `kanban_column` CHECK (inventory schema-73).

`phase_events`, altered in place (no copy-rename, so `sqlite_sequence` and the AUTOINCREMENT ids are untouched). Criterion 5's copy-rename is for a table whose key changes, which SQLite cannot alter in place: `workflow_phases`. `phase_events` keeps its key and only gains a nullable column, which `ADD COLUMN` adds in place. Both tables pass `foreign_key_check` (4.4 step 9):

```sql
ALTER TABLE phase_events ADD COLUMN entity_uuid TEXT REFERENCES entities(uuid);
-- the attribution UPDATEs of section 5.2 run here
DROP INDEX IF EXISTS idx_pe_lookup;               -- (type_id, phase, event_type)
DROP INDEX IF EXISTS idx_pe_project;              -- (project_id, event_type)
DROP INDEX IF EXISTS phase_events_backfill_dedup; -- UNIQUE(type_id, phase, event_type, timestamp)
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
```

`idx_pe_timestamp` stays.

**Dropped, and why:**

| Object | Created by | Why it goes |
|---|---|---|
| `workflow_phases.type_id` (the PRIMARY KEY) | m3 (:405-428) | the key moves to `entity_uuid`; the type_id is the entity's, read by join |
| `workflow_phases.workspace_uuid`, with its foreign key to `workspaces` | m11 (:2042-2045) | derived from the entity; a copy drifts (`backfill_project_ids` never cascaded) |
| `workflow_phases.uuid` | m6 | an unenforced copy of the entity's uuid, which is now the key; on the live file all 521 non-NULL values match (Q-stale-uuid) |
| `enforce_immutable_wp_type_id` | m3 (:433-438) | no `type_id` column; immutability moves to `entity_uuid` |
| `wp_autofill_workspace_uuid` | m11 (:2062) | nothing left to fill; it was the smallest-workspace guess |
| `wp_reject_orphaned_insert` | m11 (:2078) | replaced by `wp_reject_unknown_entity`, which checks every insert, not only those with a NULL workspace |
| `idx_wp_uuid`, `idx_wp_workspace_uuid` | m6, m11 | their columns are gone; the primary-key autoindex covers `entity_uuid` |
| `idx_pe_lookup`, `idx_pe_project` | m10 (:1525-1533) | no reader keys `phase_events` by type_id or `project_id` after the re-key |
| `phase_events_backfill_dedup` (type_id form) | m10 (:1550-1554) | re-created on `entity_uuid`, so two workspaces' backfill events can no longer collide by name |

**Views:** `entity_axis_state` is re-created where its text differs (section 4.3). `entity_state` and `entity_phase_status` are untouched.

### 4.3 Open question 11: the `entity_axis_state` text

- **Target:** views.py's `_VIEWS_DDL` text, `WHERE event_type != 'skipped'` (views.py:86-105).
- **Why:**
  - **It is the committed intent, with its reason** (views.py:65-71): "NULL-to_value rows stay visible: NULL is the DESIGNED reset semantic (phase_reset pins it)".
  - **Every rebuilt or staging file already has it.**
  - **The live text was never committed:** `WHERE to_value IS NOT NULL AND event_type != 'skipped'` matches only v2 migration 3's stale docstring (database.py:6173-6178). R2 corrects that docstring.
    - **The search:** `git log --all -G "to_value IS NOT NULL" -- plugins/pd/hooks/lib/entity_registry/views.py` prints nothing.
    - **Where the phrase occurs:** only in two commits: `cbee6257`, whose migration 3 rebuilds the view from `_VIEWS_DDL`, never from the docstring's text, and `e01ec8f0`, a docs commit (`calvin/view_text_history.out`).
- **How:** on a file with an `events` table, the migration re-creates `entity_axis_state` from `_VIEWS_DDL` when the whitespace-normalised text differs. v1-generation files have no views, so there is nothing to do.
- **Effect:** no production reader (inventory schema-70: only `bench-db-direct-read.sh` reads the views). Prototype: the live copy's and the staging file's views are identical afterwards.
- **Why this round, with nothing user-visible:** criterion 5's one target covers the whole schema. Left alone, the live file would differ from every staging file in one object, and a later fix would need its own version bump and live migration.

### 4.4 The migration, step by step

`_v2_migration_8_rekey_workflow_phases(conn)` goes in database.py after `_v2_migration_7_immutable_is_legacy` (:6348). The prototype `proto/rekey_migration.py` implements every step.

1. **Probe, outside the lock.** Three parts can be pending:
   - `workflow_phases` lacks `entity_uuid`;
   - `phase_events` lacks `entity_uuid`;
   - on a v2 file, the `entity_axis_state` text differs from the target.

   None pending → return. That makes a re-run a no-op, and covers a core-only `bootstrap_v2` file with neither table.

   **The live-path tripwire** (13.1): with rows to move (old-shape `workflow_phases` or `phase_events` rows) on the account's live registry, raise `MigrationError` naming `scripts/rekey_live_registry.py`, unless `PD_REKEY_APPLY=1` is set. Only the operator tool's `apply` sets it.
2. **Foreign keys off.** Record `PRAGMA foreign_keys`, set it OFF, and read it back. If it still reads 1, a transaction is open: raise `MigrationError` (database.py:4341, the house class for new migration gates). Migration 8 makes the same check at :1060-1065, with an older `RuntimeError`.
3. **`BEGIN IMMEDIATE`, as literal SQL.** The function runs on both connection modes: `EntityDatabase`'s legacy mode and `rebuild_tool`'s autocommit connection. v2 migration 2 does the same, for the same reason (database.py:5999-6007).
4. **Re-probe under the lock:** a peer may have finished first. Nothing pending → `ROLLBACK` (nothing was written), restore `foreign_keys` (step 11's `finally`), and return None, writing no audit row. The prototype writes an empty `success` row here; R2's code follows this step.
5. **Refuse a surprise dependent,** only when the `workflow_phases` part is pending: if any trigger on another table, or any view, names `workflow_phases`, raise `MigrationError`. There are none today (inventory 2.5).
6. **Copy-rename `workflow_phases`:**
   1. Count the rows.
   2. Write one `migration_audit_log` row per row whose `(workspace_uuid, type_id)` no entity holds, which includes a NULL workspace:
      - `rekey_row_reattached`, with the full row and the entity's current workspace, when the re-attached class's conditions hold (5.1);
      - `rekey_row_dropped`, with the full row and the reason, otherwise (the unmappable class).
   3. Write one audit row per stale stored uuid, event `rekey_stored_uuid_ignored`. Stale means `uuid` is not NULL and differs from the matched entity's uuid.
   4. `DROP TABLE IF EXISTS workflow_phases_new`, then `CREATE TABLE workflow_phases_new` with the target DDL.
   5. `INSERT INTO workflow_phases_new SELECT e.uuid, wp.workflow_phase, wp.kanban_column, wp.last_completed_phase, wp.mode, wp.backward_transition_reason, wp.updated_at FROM workflow_phases wp JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id`.
   6. Re-attach: the same copy for the re-attached class, keyed by its stored `uuid` (the exact SQL is in 5.1).
   7. Assert copied + re-attached + dropped = counted, or raise `MigrationError`.
   8. `DROP TABLE workflow_phases`: its 3 triggers and 4 indexes go with it.
   9. `ALTER TABLE workflow_phases_new RENAME TO workflow_phases`.
   10. Create the 2 indexes and 2 triggers, and assert the table's index-name set.
7. **Alter `phase_events`:** add the column, run the sole-holder and label-decided UPDATEs (section 5.2), drop the 3 indexes, and create the 2 new indexes and 2 triggers.
8. **Re-create the view (v2 files only):** `DROP VIEW entity_axis_state`, then run each statement of `_VIEWS_DDL` with `conn.execute`. Never `executescript`: it would COMMIT in the middle of the transaction.
9. **Check foreign keys,** only for tables that exist on this file: `PRAGMA foreign_key_check(workflow_phases)` and `PRAGMA foreign_key_check(phase_events)`; any row raises `MigrationError`.
   - **Why table-scoped:** an unrelated violation elsewhere in the file must not stop the file from opening.
   - **The full check** is part of verification instead; it returns 0 rows on the live copy.
10. **Audit the success:** one `success` row with the counts. Its `migration_version` is the chain generation when the migration ran: 8 when `_metadata.schema_generation` was v2, 26 otherwise. Staging-built and fresh files record 26 (a staging build runs the migration during its v1 replay, before the v2 stamp); a fresh file carries one success row with every count 0, and `test_fresh_and_staging_shapes_identical` asserts both. Every audit row of this migration (steps 6.2, 6.3 and this one) carries `"migration": "rekey_workflow_phases"` in its payload, and goes through `_append_migration_audit_log(conn, version=, event_type=, payload=)` (database.py, beside `MigrationError`).
11. **`COMMIT`.** On any exception, `ROLLBACK` and re-raise. Finally, restore `foreign_keys` to its recorded value.

The runner then stamps the version, as for every migration (`_migrate`, database.py:11078; `_migrate_v2`, :11191).
- **Concurrent openers:** the runner is serialized and its stamp monotonic (task 4C), so two processes opening a pre-rekey file run migration 26/8 once. Without that, the loser of a race can stamp 11 over 26, and migration 12 then fails at every open: R3's blast probe bricked a v10 file in 12 of 20 rounds. So RK2 waits for 4C to land on develop, or carries 4C's five-point contract and its tests itself (section 15).
- **Its race tests:** RK2 re-runs 4C's race tests with migration 26 registered (a fresh-file race, an old-file race from v10, and `test_migration_11_concurrent_runners` for 50 consecutive runs). It adds the v2-chain case `test_rekey_migration.py::test_two_runners_on_a_pre_rekey_v2_file_migrate_once`: two forked runners on a `make_pre_rekey_db(path, 'v2')` file, then a third open; the version is 8, there is one success audit row, and the third open succeeds. Step 4's in-process peer case (`test_peer_finished_first_writes_nothing`) stays. No test in any gate gets a re-run allowance.

**Resumable and idempotent,** shown by the prototype on live copies:

| Interruption | Result |
|---|---|
| process killed inside the transaction (`os._exit`, no ROLLBACK issued) | tables and schema unchanged; the next open migrates (529 rows) |
| exception raised after the copy | ROLLBACK; tables and schema unchanged; `foreign_keys` back ON |
| crash between COMMIT and the version stamp | version still 7; the next open finds nothing pending, and only `_metadata` changes (the stamp to 8) |
| re-open of a migrated file | no table changes |

### 4.5 The target is reached

`proto-results.json`, key `target_schema_identical`: the whitespace-normalised `sqlite_master` text of every object on the two tables is identical in all four files:

- the live copy (v2/8);
- the fresh file (v1/26);
- the staging file (v2/8);
- the class fixture (v1/26).

The live copy's views equal the staging file's (`views_identical_live_vs_staging`). `PRAGMA integrity_check` returns `ok` on each file.

## 5. Data migration rules

### 5.1 `workflow_phases` rows (529 live)

| Class | Rule | Live rows | Proved by |
|---|---|---|---|
| **matched:** an entity holds the row's `(workspace_uuid, type_id)` | copy, keyed by that entity's uuid, with the state columns verbatim | 529 | Q-rows-kept |
| **null-uuid:** the stored `uuid` is NULL | as matched; the stored `uuid` is never consulted | 8, all pedantic-drip: `backlog:278`–`284` and `feature:134-workflow-rebuild` | Q-null-uuid |
| **stale-uuid:** the stored `uuid` disagrees with the matched entity | copy by the match; audit `rekey_stored_uuid_ignored` | 0 | Q-stale-uuid |
| **archived:** the entity is archived | copy: the row stays with its entity, since archiving is a flag | 163 | Q-archive-flags |
| **soft-deleted:** the entity is soft-deleted | copy, keeping `set_deleted`'s round trip lossless | 0: no live entity is soft-deleted | Q-archive-flags |
| **shared:** the type_id is shared | copy with the entity the row is attached to today | 5, all pedantic-drip | Q-shared |
| **re-attached:** no entity holds the pair, but the stored `uuid` names an entity that no row matches by pair and that no other row's `uuid` names | copy, keyed by that stored uuid; audit `rekey_row_reattached` | 0 | Q-unmappable |
| **unmappable:** no entity holds the pair, or `workspace_uuid` is NULL, and the row is not re-attached | not copied; each recorded in `migration_audit_log` as `rekey_row_dropped` | 0 | Q-unmappable |

- **How the classes add up:** matched, re-attached and unmappable partition the rows (529 + 0 + 0 live). Null-uuid, stale-uuid, archived, soft-deleted and shared are facets inside matched, so the column does not sum.
- **Why stale-uuid is audited, not refused:** the `(workspace_uuid, type_id)` pair is what every reader and W3.1's join used, so copying by it preserves observable behaviour. Refusing would make a file with one stale copy unopenable for every pd process.
- **Why re-attached rows are kept:** `backfill_project_ids` and `claim_unknown_entities` re-attribute entities without touching their rows (1.1), so a row's stored workspace can go stale while its stored `uuid` still names its entity.
  - **Today's readers** join by type_id alone (database.py:10461), so they still show that row under its entity; keying it by the stored uuid keeps that.
  - **The conditions** keep two rows from claiming one entity: the entity has no row matched by pair, and no other row carries its uuid.
- **Why unmappable is dropped with a record, not refused:** a NULL-workspace row with no usable uuid is a pre-migration-11 orphan (m11's backfill found no entity for it). Attaching it to an entity registered later would give that entity stale state; a uuid-keyed re-attach can't do that, since a later entity has a new uuid. Refusing would make the file unopenable. The audit row keeps the data.

The re-attach copy (4.4 step 6.6):

```sql
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
```

Checked on a synthetic old-shape file with one row of each kind (`calvin/reattach_probe.out`): the stale-workspace row is re-attached; a NULL-workspace row, a row whose uuid names an entity another row holds by pair, and two rows sharing one uuid are dropped.

The verification queries. "Pre" runs on the backup (old shape); "post" on the migrated file. Expected values are the live copy's, and the prototype got every one.

```sql
-- Q-rows-kept: state preserved exactly. Compare the two sets in the verifier (Python):
-- |pre| = |post| = 529, pre - post = post - pre = {}.
-- pre: the matched rows plus the re-attached rows, each keyed by its entity's current
-- (workspace_uuid, type_id); the second SELECT's WHERE is the re-attach copy's (0 rows live):
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
-- (an orphan NULL-uuid pair, which the migration drops, is not listed):
SELECT wp.workspace_uuid, wp.type_id FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
WHERE wp.uuid IS NULL;
-- post: each listed pair has a row (8).

-- Q-stale-uuid: pre, stale stored uuids -> 0
SELECT count(*) FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
WHERE wp.uuid IS NOT NULL AND wp.uuid <> e.uuid;
-- post: every stored uuid is now a key -> 521
SELECT count(*) FROM workflow_phases WHERE entity_uuid IN (<pre: SELECT uuid FROM workflow_phases WHERE uuid IS NOT NULL>);

-- Q-archive-flags: rows by entity flags -> (0,0,366), (1,0,163)
SELECT e.is_archived, e.is_deleted, count(*) FROM workflow_phases wp
JOIN entities e ON e.uuid = wp.entity_uuid GROUP BY 1, 2 ORDER BY 1, 2;

-- Q-shared: shared type_ids -> the 5 type_ids, each with workspace 69696982-0e18-46f1-acf2-18a3edc6bbb7
SELECT e.type_id, e.workspace_uuid FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid
WHERE (SELECT count(*) FROM entities x WHERE x.type_id = e.type_id) > 1 ORDER BY 1;

-- Q-unmappable: pre, rows whose pair no entity holds -> 0 ; post, re-attached plus dropped audit rows -> 0 (the same number)
SELECT count(*) FROM workflow_phases wp WHERE NOT EXISTS (
  SELECT 1 FROM entities e WHERE e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id);
SELECT count(*) FROM migration_audit_log WHERE event_type IN ('rekey_row_reattached', 'rekey_row_dropped');

-- Q-keys: keys -> 529 rows, 0 without an entity, foreign_key_check empty
SELECT count(*) FROM workflow_phases;
SELECT count(*) FROM workflow_phases wp LEFT JOIN entities e ON e.uuid = wp.entity_uuid WHERE e.uuid IS NULL;
PRAGMA foreign_key_check(workflow_phases);
```

**The class fixture** (prototype `classes-v1.db`: a fresh v1 file seeded by raw SQL with what the live file lacks) exercised the stale-uuid and unmappable classes. Its NULL-workspace orphan was dropped and audited; its stale-uuid row was audited and copied by its pair. R4's seeding helper adds a re-attached row (open question 22).

### 5.2 `phase_events` rows (1469 live)

The rules of section 3.3, as the exact SQL the migration runs (after the ADD COLUMN):

```sql
-- sole-holder: the type_id's only holder
UPDATE phase_events SET entity_uuid =
  (SELECT e.uuid FROM entities e WHERE e.type_id = phase_events.type_id)
WHERE entity_uuid IS NULL
  AND (SELECT count(*) FROM entities e WHERE e.type_id = phase_events.type_id) = 1;

-- label-decided: several holders; the label names one holder's workspace, by its
-- legacy id or its uuid; '__unknown__' never decides
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

-- undecided and no-holder: no statement; entity_uuid stays NULL.
```

- **Holders include soft-deleted entities,** as `_resolve_identifier` counts them. That is right for history: an event may belong to an entity deleted since.
- **The label-decided lookup is unique:** `project_id_legacy` is UNIQUE, a legacy id (12 hex characters) never equals a workspace uuid, and entities are unique per `(workspace, type_id)`.
- **A uuid label decides:** since 1B, the cascade writer labels an event with its workspace's uuid when that workspace has no legacy id (3.2). No live label is a uuid today.
- **`'__unknown__'` never decides:** it is the unknown workspace's legacy id (workspace `6250c8a6…`), so without that condition an event carrying it would be pinned on that workspace's namesake, if it ever held a shared type_id. It holds 0 entities today, and 285 of the 1469 live events carry the label (272 sole-holder, 13 undecided).
- **Neither condition changes a live figure.** RK2's `test_event_classes_follow_the_attribution_rules` adds a case for each: a uuid label decides, and an `'__unknown__'` label stays undecided even when the unknown workspace holds the type_id.

```sql
-- Q-attributed: attributed -> 1444
SELECT count(*) FROM phase_events WHERE entity_uuid IS NOT NULL;
-- Q-unattributed: unattributed, by holder count -> {0: 12, 2: 13}
SELECT (SELECT count(*) FROM entities e WHERE e.type_id = pe.type_id) AS holders, count(*)
FROM phase_events pe WHERE entity_uuid IS NULL GROUP BY 1 ORDER BY 1;
-- Q-misattributed: no event attributed to an entity with another type_id -> 0
SELECT count(*) FROM phase_events pe JOIN entities e ON e.uuid = pe.entity_uuid WHERE e.type_id <> pe.type_id;
-- Q-event-count: nothing added or lost -> 1469, max(id) 1469, sqlite_sequence 1469
SELECT count(*), max(id), (SELECT seq FROM sqlite_sequence WHERE name = 'phase_events') FROM phase_events;
-- Q-event-fk: foreign keys -> empty
PRAGMA foreign_key_check(phase_events);
-- Q-audit: the success row -> exactly one: 529 copied, 0 re-attached, 0 dropped, 0 stale; events 1436 / 8 / 25
SELECT migration_version, payload FROM migration_audit_log
WHERE event_type = 'success' AND payload LIKE '%"migration": "rekey_workflow_phases"%';
-- Q-audit-rows: the per-row audit rows, by event -> none on the live copy; one per seeded case on the class fixture
SELECT event_type, count(*) FROM migration_audit_log
WHERE event_type IN ('rekey_row_reattached', 'rekey_row_dropped', 'rekey_stored_uuid_ignored')
  AND payload LIKE '%"migration": "rekey_workflow_phases"%' GROUP BY 1;
```

**Expected figures on any file** (13.3 step 2). Every "pre" query of 5.1 and the re-attach `SELECT`, run on the backup, gives the expected row figures. This query gives the expected event figures, by the UPDATEs' own predicates:

```sql
-- sole-holder, label-decided, undecided, no-holder -> 1436, 8, 13, 12 on the live copy
SELECT sum(h = 1), sum(h > 1 AND lbl IS NOT NULL), sum(h > 1 AND lbl IS NULL), sum(h = 0) FROM (
  SELECT (SELECT count(*) FROM entities e WHERE e.type_id = pe.type_id) AS h,
         (SELECT e.uuid FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid
           WHERE e.type_id = pe.type_id
             AND (w.project_id_legacy = pe.project_id OR w.uuid = pe.project_id)
             AND pe.project_id <> '__unknown__') AS lbl
  FROM phase_events pe);
```

Checked on the prototype's backup of the live copy (`calvin/live_class_counts.out`): rows 529 matched, 0 re-attached, 0 dropped; events 1436, 8, 13, 12.

### 5.3 The shared type_ids after the migration

- **The 5 rows stay with pedantic-drip's entities.**
- **terry_agent's five namesakes** (all archived) stay row-less until terry_agent's entity server starts. Its startup backfill (W2.6) then seeds their own rows: `backfill_workflow_phases` lists every entity of its workspace except projects, archived ones included (backfill.py:253-254). Being archived, they get no board card.
  - **Before RK1 scopes the backfill's row check,** it would skip them: it asks `get_workflow_phase(type_id)` with no workspace (backfill.py:284, :346) and finds pedantic-drip's row.
- **`feature:035-slim-watchdog-self-mgmt`** (both holders archived, no rows): the migration leaves both row-less. Afterwards each workspace's backfill seeds its own namesake a row when that workspace's entity server starts. Before the re-key, the first workspace to backfill takes the only row, and the other's backfill skips (the row check above).
- **Unaffected:** `project:P001` (projects get no rows).
- **An observation the re-key does not act on:** the artifacts of pedantic-drip's five namesakes exist only in `/Users/terry_agent/docs`: `features/002`–`004` and both brainstorm PRDs (checked with `ls`; absent from `/Users/terry/projects/pedantic-drip/docs`).
  - **What it suggests:** they look like terry_agent history registered under pedantic-drip in March, before workspace scoping.
  - **What the migration does:** keeps today's attachment. It changes keys, not facts.
  - **Their state:** pedantic-drip's five are not archived (two promoted brainstorms, and features 002–004, completed at finish), so they show on its board; terry_agent holds all five archived.
  - **What remains:** archiving or merging them is a data decision for the user (Q6, section 9; the Deferred table in section 14). Re-attributing them to terry_agent is impossible: it already holds all five, so `UNIQUE(workspace_uuid, type_id)` refuses a second row, and after the re-key `enforce_immutable_wp_entity_uuid` forbids re-pointing a row.
- **The other tables** (`entities`, `events`, `entity_relations` and the rest) are untouched.

## 6. API contract

### 6.1 The naming rule

One rule covers every `EntityDatabase` method that names one entity: the 20 method-and-parameter pairs of `ENTITY_NAMING_METHODS` (6.3), which the guard checks complete (section 11). It puts three rev 2.1 contracts into a single library contract:
- W2.1: "type_id plus the caller's workspace";
- W3.4: a type_id resolves "in the caller's workspace", and an explicit uuid "passes through unchanged";
- D5: an explicit uuid "may still point anywhere".

The rule:
- **A uuid names an entity in any workspace.** This is `_resolve_identifier`'s uuid branch, unchanged (database.py:7017-7024).
  - **It returns before it reads any workspace,** so a uuid passed with another entity's workspace still names the uuid's entity.
  - **That is not a silent cross-workspace write** in plan:240's sense: the caller named that one entity by its identity, as D5 allows. The hazard plan:240 names is a type_id reaching a namesake's row.
  - **Test:** `test_uuid_resolves_its_entity_whatever_the_workspace[<pair>]`, over the 15 pairs whose parameter is an identifier RK1 resolves: `resolve_ref.ref`, `set_parent.type_id`, `set_parent.parent_type_id`, `reparent_entity.type_id`, `get_entity.type_id`, `feature_entity_id.type_id`, `get_lineage.type_id`, `set_archived.type_id`, `set_deleted.type_id`, `update_entity.type_id`, `delete_entity.type_id`, `export_lineage_markdown.type_id`, `create_workflow_phase.type_id`, `get_workflow_phase.type_id` and `upsert_workflow_phase.type_id`.
    - **Red on RK1's base** for five: the three new keywords (`get_entity`, `get_workflow_phase`, `feature_entity_id`: a `TypeError`) and the two flag writers (`set_archived`, `set_deleted`: a uuid passed with another workspace raises). **Keep-green** for the other ten. The implementer records each case's base outcome; a case the base run shows red is recorded red, with its reason.
    - **No case** for `resolve_entity_uuid.type_id` or `search_by_type_id_prefix.prefix`: they take type_id text by contract, not an identifier (6.3).
    - **RK2 adds** `update_workflow_phase.type_id`, `append_phase_event.type_id` and `query_phase_events.type_id`, once rows and events are keyed by entity uuid.
- **A type_id names an entity only together with a workspace.** The workspace is `workspace_uuid`, or the deprecated `project_id` alias on the methods that already accept it, except `append_phase_event`, whose `project_id` is the event's label (3.2). The lookup runs inside that workspace only.
  - **The alias resolves as `_resolve_optional_workspace_filter` does today** (database.py:6896-6977): `'__unknown__'` names the unknown workspace; any other value names the workspace whose `project_id_legacy` it is, or raises `ValueError` when none is. Given both, `workspace_uuid` wins, with a `DeprecationWarning`.
  - **`'*'` is not a workspace.** List and export tools turn it into "no filter" before they call the library (entity_server.py:1205, :1248, :1448; workflow_state_server.py:2406-2448). Passed as an entity's workspace, it raises like any label no workspaces row holds.
- **A type_id with no workspace raises `WorkspaceRequiredError`,** a `ValueError` subclass, even when only one workspace holds it. The message names the parameter: `<parameter> '<value>' needs a workspace_uuid: a type_id names an entity only inside one workspace`, for example `prefix 'feature:05' needs a workspace_uuid: …`. Tests match only `needs a workspace_uuid`.
  - **It is never swallowed:** `get_entity`, `get_lineage` and every not-found handler in database.py (`feature_entity_id`, `get_workflow_phase`, `update_workflow_phase`, `set_archived`, `set_deleted`, `query_phase_events`) re-raise it, never turning it into None, `[]` or not found. Today `get_entity` answers None for any `ValueError` (database.py:8229-8232), and `get_lineage` answers `[]`. Callers above the library follow the same rule (section 8).
- **Where it lives:** `_resolve_identifier` (database.py:6983-7057) loses its "No scope: must be globally unique" branch (:7041-7057). Every method in 6.3 resolves through it once, then reads and writes by the entity uuid.
- **Lists and searches name no entity,** so no workspace still means every workspace:
  - `list_entities` and `search_entities`;
  - `list_workflow_phases`;
  - `query_phase_events` when no entity is named.

  `search_by_type_id_prefix` is not one of them. At `ddc299a0` its production callers are `resolve_ref` (database.py:7245) and 1C's `_another_workspace_holds` (entity_status.py:256), the unscoped check behind 1C's skip. After RK2, `resolve_ref` is the only one, and its answer names one entity, so the method follows the rule and needs a workspace (6.3).
- **1C's skip goes in RK2,** before RK4 makes the prefix search strict. RK2 deletes `_another_workspace_holds` (entity_status.py:244-257), the skip branch in `_sync_brainstorm_entities` (:160-167) and the docstring's skip paragraph (:21). The skip's own condition, "until workflow rows are keyed per entity", is what RK2's flip meets.
  - **Afterwards:** a brainstorm file whose type_id only another workspace holds registers in the session's workspace as its own namesake. `_workspace_holds` (:228-241, scoped) stays.
  - **Its tests are rewritten,** red on RK2's base: `test_a_type_id_only_another_workspace_holds_is_skipped_and_named[none|archived|soft_deleted]` (test_brainstorm_registration_scoped.py:327) becomes `test_a_type_id_only_another_workspace_holds_registers_here[...]`: a new entity in the session's workspace, the other workspace's entity and row unchanged, and no warning names it. `test_a_second_session_start_after_the_skip_changes_nothing` (:419) becomes `..._after_the_registration_changes_nothing`, and :443's parameter `skipped-held-by-B` becomes `registered-beside-B`. The 7 failures the strict rule causes in `test_c5b_brainstorm_workspace.py`, `test_entity_status.py` and `test_orchestrator.py` are expected to go green once the skip goes; any test that pins the skip is rewritten the same way.
- **The library already works this way in places:**
  - `register_entity` refuses a missing workspace: `register_entity() requires workspace_uuid` (database.py:7679-7680);
  - `resolve_entity_uuid(workspace_uuid, type_id)` (:7159) takes one.
- **Why not keep "globally unique is fine":** that fallback is the cross-workspace path criterion 4 forbids.
  - **Today:** a type_id that only B holds resolves to B's entity. Rev 2.1's own W3 test records this: "`update_entity` by type_id: from workspace A, with a type_id only B holds, it answers not-found. Today it updates B's entity" (design:398).
  - **After the re-key:** the fallback would reach B's row too, through B's uuid. So it goes at the library, not only at the MCP boundary.

### 6.2 The row view

Every method that returns a `workflow_phases` row returns this shape:

| Key | Source |
|---|---|
| `entity_uuid` | the row's key |
| `type_id`, `workspace_uuid` | the entity, read in the same SELECT: its current identity, never stored |
| `workflow_phase`, `kanban_column`, `last_completed_phase`, `mode`, `backward_transition_reason`, `updated_at` | the row |
| `execution_status`, `pipeline_phase`, `entity_name`, `entity_type`, `entity_artifact_path` | `list_workflow_phases` only, as today (database.py:10453-10461) |

- **One SELECT serves every method:** `SELECT wp.*, e.type_id, e.workspace_uuid FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid`. It is a module constant beside the table's DDL.
- **The `uuid` key goes.** It was the table's copy of the entity's uuid, and `entity_uuid` replaces it.
  - **At `4a6373f0`, no production reader takes `uuid` from these methods' results:** a grep of the scan roots finds no `["uuid"]` read on them, and every `.get("uuid")` read and template `.uuid` read is on an entity or workspace dict (`calvin/uuid_reads.out`).
  - **A reader missed later** fails loudly only if it reads `["uuid"]` (a `KeyError`); one that reads `.get("uuid")`, or a template, gets None or an empty string silently. So RK2's reviewer re-runs both greps on the landed code, and Phase R's per-rebase checklist re-runs them, with a grep for `row['type_id']` and `.get('uuid')`, on the code each rebase brings in (section 15).
  - **The test readers** change in RK2.
- **Why the `type_id` and `workspace_uuid` keys stay:** they are read from the entity at query time, so they cannot drift (criterion 3). Readers of `row["type_id"]` keep working.

### 6.3 Per method

Signatures are from `4a6373f0` (`work/scan` and the AST dump of the export) and unchanged at develop `c1bbfae0`; line numbers are at `c1bbfae0`.
- **No parameter is renamed.** The naming rule applies to the value passed, a uuid or a type_id, whatever the parameter is called, so keyword callers are unaffected, and no task has renames to make.
- **`ENTITY_NAMING_METHODS`** lists each method below with the parameter that names an entity: 20 pairs once `delete_workflow_phase` is deleted. They are `resolve_ref.ref`, `search_by_type_id_prefix.prefix`, `resolve_entity_uuid.type_id`, `set_parent.type_id`, `set_parent.parent_type_id`, `reparent_entity.type_id`, `get_entity.type_id`, `feature_entity_id.type_id`, `get_lineage.type_id`, `set_archived.type_id`, `set_deleted.type_id`, `update_entity.type_id`, `delete_entity.type_id`, `export_lineage_markdown.type_id`, `append_phase_event.type_id`, `query_phase_events.type_id`, `create_workflow_phase.type_id`, `get_workflow_phase.type_id`, `update_workflow_phase.type_id` and `upsert_workflow_phase.type_id`. A uuid names its entity in every pair except `resolve_entity_uuid.type_id` and `search_by_type_id_prefix.prefix`, which take type_id text by contract. RK5 declares the list from the code it lands on, and the guard's scan keeps it complete (section 11).

| Method | After the re-key | What changes |
|---|---|---|
| `_resolve_identifier(identifier, project_id=None, *, workspace_uuid=None)` :6983 | same signature | a type_id with no workspace raises (6.1) |
| `get_entity(type_id, *, include_deleted=False)` :8215 | `get_entity(type_id, *, workspace_uuid=None, include_deleted=False)` | resolves by the rule; None when nothing matches; raises on a type_id with no workspace. Today it takes no workspace, and answers None for a shared type_id |
| `resolve_ref(ref, project_id=None, *, workspace_uuid=None)` :7180 | same signature | the exact and prefix branches run only inside the workspace. The unscoped exact match, which took the first row (:7236-7239), goes |
| `search_by_type_id_prefix(prefix, project_id=None, *, workspace_uuid=None)` :7283 | the workspace becomes required | its production callers at `ddc299a0` are `resolve_ref` (:7245), which always passes one, and 1C's `_another_workspace_holds` (entity_status.py:256), which RK2 deletes (6.1). It takes type_id text by contract, not an identifier, so it has no uuid case |
| `resolve_entity_uuid(workspace_uuid, type_id)` :7159 | same signature | raises `WorkspaceRequiredError` on a missing workspace (6.1); today `WHERE workspace_uuid = NULL` answers `(None, None)`. It takes type_id text by contract, so it has no uuid case |
| `feature_entity_id(type_id)` :8250 | `feature_entity_id(type_id, *, workspace_uuid=None)` | reads the resolved entity's `entity_id`, no longer every namesake's. The directory helpers gain a keyword `workspace_uuid`, used only when they read the registry: `feature_dir_name` and `feature_dir_path` (feature_paths.py:70, :113) and `engine._feature_dir_name` (engine.py:394). Their callers pass the workspace they hold: `transition_phase`'s own (engine.py:149); `validate_prerequisites`' (:259), which gains one, as `get_state` does; `activate_feature`'s, through `_validate_feature_type_id` (feature_lifecycle.py:133, called at :591); the resolved feature's `workspace_uuid` in `promote_task` (task_promotion.py:327) and in `_artifact_dir` (workflow_state_server.py:422); and `check_workflow_drift`'s, through `_read_single_meta_json` and `_single_feature_dir_name` (reconciliation.py:189, :210, :577, :580). The `use_db=False` calls (engine.py:256, :262, :531) read no registry and need none; the call at engine.py:603 (at `4a6373f0`) went with W1's hydration. Three tests that read every namesake's value at once lose their subject: RK1 rewrites `test_c11_feature_entity_id.py::test_a_type_id_held_in_two_workspaces_answers_once` to pass each workspace's `workspace_uuid` and assert each answers its own `entity_id` (`003-shared`), and deletes `test_c11_feature_entity_id.py::test_two_distinct_values_for_one_type_id_are_refused` and `test_c11_feature_paths.py::test_disagreeing_rows_are_refused` |
| `get_lineage` :8346, `set_parent` :7943, `reparent_entity` :8099, `export_lineage_markdown` :9374 | same signatures | every ref resolves by the rule; a parent uuid may name another workspace (D5) |
| `update_entity(type_id, …, *, workspace_uuid=None)` :8516 | same signature | the rule applies. The `workflow_phases` re-attribution cascade (:8773-8788) is deleted, because nothing is left to cascade |
| `delete_entity(type_id, project_id=None, *, workspace_uuid=None)` :8977 | same signature | the rule applies. Soft delete keeps the row, and the docstring's claim that it deletes `workflow_phases` rows (:8984-8990) is corrected |
| `set_archived(type_id, archived=True, *, workspace_uuid=None, actor=…)` :8436 | same signature | resolves by the rule, then runs `UPDATE entities … WHERE uuid = ?`. Since 1B it already takes a uuid, through its by-uuid branch (:8466-8471), so W1.2's uuid call works as written (open question 1). A type_id with no workspace still archives every namesake (:8466-8475) until RK1 resolves it |
| `set_deleted(type_id, deleted=True, *, workspace_uuid=None)` :8484 | same signature | as `set_archived`, and it gains the uuid path `set_archived` has had since 1B. Today it has none: a uuid raises "no entity with type_id '<uuid>'", and a type_id with no workspace soft-deletes every namesake (`WHERE type_id = ?`, :8505) |
| `create_workflow_phase(type_id, *, workspace_uuid=None, …)` :9986 | same signature | resolves by the rule, then runs `INSERT (entity_uuid, <state columns>)`. A second row for the entity fails on the primary key and raises today's "already exists" `ValueError`. The `workflow_established` emit (:10070-10072) is unchanged. It returns the row view |
| `get_workflow_phase(type_id)` :10092 | `get_workflow_phase(type_id, *, workspace_uuid=None)` | returns the row view, or None when the entity is unknown or has no row |
| `update_workflow_phase(type_id, *, …, workspace_uuid=None)` :10102 | same signature | runs `UPDATE … WHERE entity_uuid = ?`; with no row it raises `Workflow phase not found`. The stored-workspace assertion (:10169-10188) goes, because a row can't belong to another workspace. The four tests that pin its `workspace_uuid mismatch` (`TestEngineWorkspaceUuidForwarding`'s three, test_engine.py:3526-3611; `TestUpdateWorkflowPhaseWorkspaceUuidAssertion`, test_database.py:4160-4203) keep their subject, the engine forwarding the workspace, and now expect `Workflow phase not found`, with nothing written |
| `upsert_workflow_phase(type_id, project_id=None, *, workspace_uuid=None, **kwargs)` :10229 | same signature | runs `INSERT … ON CONFLICT(entity_uuid) DO UPDATE SET <given columns>`. The branch that refuses another workspace's row (docstring :10247) goes: A's call writes A's row |
| `delete_workflow_phase(type_id)` :10373 | **deleted** | no production caller (only `test_database.py`, 4 calls), so one writer keyed by type_id goes |
| `list_workflow_phases(*, kanban_column=None, workflow_phase=None, workspace_uuid=None, include_archived=True)` :10393 | same signature | an inner join on `entity_uuid`, filtering on `e.workspace_uuid`. The `OR e.uuid IS NULL` orphan clauses (:10442, :10448) go (section 7) |
| `append_phase_event(*, type_id, project_id, event_type, …, workspace_uuid=None, metadata=None)` :9620 | adds `entity_uuid=None`; `type_id` becomes optional when `entity_uuid` is given | see below the table |
| `query_phase_events(*, type_id=None, project_id=None, phase=None, event_type=None, limit=50)` :9841 | adds `entity_uuid=None` and `workspace_uuid=None` | see below the table |
| `query_phase_events_bulk(type_ids, event_types=None)` :9879 | `query_phase_events_bulk(entity_uuids, event_types=None)` | keyed by entity uuid. Its one caller, `_detect_phase_events_drift` (workflow_state_server.py:1772-1817), holds the entities' uuids. It refuses (`ValueError`) any element that is not a uuid: a missed caller that passes type_ids would otherwise get `[]` and report drift for every entity (`test_rekey_event_streams.py::test_bulk_read_refuses_type_ids`) |
| `backfill_project_ids` :8818, `claim_unknown_entities` :9130 | unchanged | they re-attribute entities. With no workspace copy left in `workflow_phases`, there is no copy for them to miss (inventory schema-47, schema-48) |

**`append_phase_event`.** It resolves the entity once: by `entity_uuid`, or by `type_id` with `workspace_uuid`.
- **Its `project_id` is never an alias:** it is the label (3.2). Every production writer already passes a `workspace_uuid` (3.1), so each write resolves by it, never by a label that names another workspace for 381 of the 1469 live events.
- **Both given, and disagreeing:** an `entity_uuid` with a `type_id` that is not that entity's raises `ValueError`. Given `entity_uuid` alone, the label is the entity's type_id.

Then, in its one transaction (:9743):
- **The INSERT** (:9746) stores `entity_uuid`, with two labels:
  - `type_id`, the entity's;
  - `project_id`, as passed (3.2).
- **The status UPDATE** (:9772) is keyed by the entity uuid.
- **The step-5 projection** becomes `UPDATE workflow_phases … WHERE entity_uuid = ?`. Today it is keyed by type_id alone (:9790).
- **The v2 dual-write** (:9810-9830) uses the same entity, so the unscoped fallback SELECT (:9823) goes.
- **An unknown entity raises `ValueError`,** for any `source`.

**`query_phase_events`.** Which rows it returns depends on what is given:
- **An entity** (a uuid, or a type_id with a workspace): the rows whose `pe.entity_uuid` matches.
- **A workspace alone** (`workspace_uuid`, or `project_id` as its alias): the rows whose attributed entity is in that workspace, found through a join.
- **Nothing:** every row, unattributed ones included.

The label columns are never filtered on again. That replaces today's `type_id = ?` and `project_id = ?` conditions (:9854, :9857).

### 6.4 Churn

Counted by `work/scan/churn_totals.py` at `4a6373f0` (output `churn_totals.out`). It counts calls of a fixed list of naming methods that pass no `workspace_uuid`, `project_id` or `entity_uuid` keyword, and whose first argument is not visibly a uuid. **It is an estimate, not a bound:**
- **Over-counts:** a uuid passed through a neutral name, or by keyword; and MCP tool functions named like library methods, such as `server.set_parent(type_id=entity_a_uuid, …)`, which passes uuids.
- **Misses** (`calvin/churn_gaps.out`):
  - 55 test calls of `append_phase_event` that pass only the `project_id` label: the count skips them, since every call passes `project_id`;
  - the feature-directory helpers (6.3), which are not on its list: 15 production and 23 test calls;
  - calls through `getattr` or a function reference;
  - label-only calls, which pass `project_id=` and no `workspace_uuid=`: the count treats them as scoped, but they are not (6.5). R3 found 28 in production at `5cc2ab75`.

| | Row APIs | Entity APIs | Engine methods | Total |
|---|---|---|---|---|
| Production | 33 | 57 | 9 | **99** |
| Tests | 544 | 564 | 132 | **1240** |

With the misses, the estimate at `4a6373f0` was about 115 production and 1320 test calls, about 1430 in all.

**Re-measured at `ddc299a0`** (R3's blast census, on develop `c1bbfae0`'s code):
- **Static re-count:** 1201 test calls in 66 files (row methods 516, entity methods 558, engine list 127). 804 of them are in 10 files over 1,500 lines: `test_database.py` has 297 in 9,639 lines, and `test_workflow_state_server.py` 418 in 11,169.
- **Record-only census** (a G1 run that records each would-be refusal instead of raising it): 1057 direct call sites in 63 files (25 of them in UI tests, RK3's), plus 754 entry-point sites that reach a refusal through production code. Of those, 159 call engine methods on the codemod's method list; 343 go through other engine and helper functions and 250 through MCP handlers, all outside it. 10 more call the private `_resolve_identifier`.
- **Production:** 88 census sites, plus the 28 label-only calls above: about 115.
- **Under the full rule, before any task's edits,** G1 fails 1451 tests: 961 are the codemod's (54 files), 196 RK1's library half, 159 RK2's, 63 RK1's MCP half, 54 RK3's, and 18 fail through 1C's skip (6.1). 541 distinct first-refusing call sites unblock the 961, and four fixtures account for 257 of those tests.

So the estimate is now about 1,800 test call sites (1057 direct and 754 entry-point) and about 115 production calls. Each codemod slice re-measures on its own base (section 15).

- **Production:** each site passes a workspace it already has (section 8).
- **Tests:** mostly mechanical, but not one workspace per file.
  - **Every test entity's workspace is written in its test:** the library refuses a registration without one (`register_entity() requires workspace_uuid`, database.py:7679-7680).
  - **But 29 of the 77 test files that register entities** use more than one workspace expression at `4a6373f0` (`calvin/codemod_workspace_scopes.out`; a file-level upper bound), and 30 of 81 at `5cc2ab75`. Each codemod slice re-measures on its base.
  - **So the codemod (RK4) works per test function:** with one workspace expression in scope (the function and the fixtures it uses), it adds `workspace_uuid=<that expression>` to each call. With two or more, or none it can read, it leaves the calls and lists them; RK4's implementer edits each by hand, taking the workspace from that entity's registration. Its method list adds every engine, helper and MCP-handler entry point that takes a workspace (the entry-point table, section 8). R3's premortem measured its scope at `5cc2ab75`: 541 calls in one-workspace functions, 173 in several-workspace ones, and 411 with no workspace in the body.
  - **A call that names entities of two workspaces** passes their uuids instead, as feature 129's `set_parent` pair does (section 12).

  This is the cost of the strict rule; it is the user's Q2 (section 9).
- **What each key choice would add:** the key choice itself adds about 109 test SQL statements under A (section 2.3), against about 56 or 38 under B or C.

### 6.5 The MCP boundary

Open question 5: for a call that names an entity, both servers hand the library a workspace uuid, never the legacy label. Lists, searches and exports, which name no entity (6.1), may still pass the legacy label or `'*'` as a workspace filter. The library resolves it to a workspace uuid (6.1) and never compares it with a label column.
- **A label-only call counts as unscoped:** a call that names an entity with `project_id=` and no `workspace_uuid=` passes the workspace or a uuid instead. At `5cc2ab75` there are 28 such production calls: 20 in entity_server.py (for example `_resolve_ref_param(..., project_id=_effective_project_id())`), 5 in workflow_state_server.py, two in backfill.py and one in server_helpers.py. A label cannot name 7 of the 21 live workspaces, which have no legacy id. So the naming-rule tests (`test_naming_rule.py`, and the servers' `test_read_tools_resolve_in_workspace.py`) add to their fixtures a workspace whose `project_id_legacy` is NULL, holding a namesake, and run each case against it too.
- **The workflow server:** every tool argument that names an entity (`feature_type_id`, `type_id`, `ref` or `entity_ref`) resolves inside `_require_workspace()` (W4.1).
  - **Which tools** (an AST scan of the tool definitions at `4a6373f0`, less `reconcile_apply`, which W1 deletes): the write tools W4.1 already covers, and these read tools:
    - `get_phase`, `get_mini_spec`, `validate_prerequisites` and `reproject_meta_json`;
    - `reconcile_check` and `reconcile_frontmatter`;
    - `get_progress_view`;
    - `query_phase_analytics`' `feature_type_id` filter;
    - `record_backward_event`'s reads.
  - **The three list tools** (`list_features_by_phase`, `list_features_by_status`, `query_ready_tasks`), if the user agrees (open question 7; Q3, section 9):
    - **`project_id` omitted:** they scope to `_require_workspace()`, which refuses when the workspace is unresolved. Today they fall back to every workspace then (`_workspace_uuid or None`, workflow_state_server.py:2448).
    - **`project_id` keeps its other two meanings:** `'*'` lists every workspace, as an explicit opt-in, and a legacy id lists its workspace or answers `invalid_project_id`, as today (:2406-2448).
  - **`query_phase_analytics`** keeps `project_id='*'` meaning every workspace.
- **The entity server:** `_resolve_ref_param` (W3.4, entity_server.py:316-360) resolves in `_require_workspace()`'s workspace. The read tools that name an entity do the same: `get_entity`, `get_lineage`, `export_lineage_markdown`'s `type_id`, `get_entity_tags` and `get_okr_alignments`. `_effective_project_id()` survives only as the filter of list and export tools that accept `'*'`.
- **Parameters and replies don't change,** so no command or skill markdown changes (open question 6).
  - **The markdown callers of the list tools** (`create-feature.md:12`, `list-features.md:11`, `workflow-state/SKILL.md:10`) omit `project_id` and never pass `'*'`. The one change they can see is the `workspace_unresolved` envelope in a session whose workspace is unresolved, which `list-features.md` already surfaces verbatim (:15).
  - **No markdown passes another workspace's type_id.**
- **Errors:**
  - a type_id not found in the caller's workspace answers the existing not-found envelope;
  - an unresolved workspace answers `workspace_unresolved` (W4.1).

## 7. W3.1–W3.3, restated for the new key

The contract rev 2.1 set, and the plan's 2B note kept, still holds: "one card per row, working links, no silent cross-workspace write" (plan:240). Each item below says what changes, with the check that shows it.

**W3.1: the board query** (`list_workflow_phases`, database.py:10393-10467).
- **The join:** `FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid`. It is an inner join: pd's code can no longer create an orphan row (section 4.2), and one that a raw-SQL delete leaves is the doctor's to report (section 14), not the board's to show.
- **The selected columns:** `wp.entity_uuid`, the row view's derived keys and today's aliases.
- **The workspace filter:** `e.workspace_uuid = ?`. It is the entity's own workspace, because there is no row copy to read instead.
- **Orphans:** the clause "an orphan row shows only in the all-workspaces view" has no subject any more. Its test becomes a schema test: inserting a row for an unknown entity is refused (prototype `guard_insert_unknown_entity`).
- **The UI's three cookie states** (`effective_workspace_uuid`, ui/routes/helpers.py:51-65): no cookie selects the startup workspace (`app.state.workspace_uuid`, resolved read-only at start, ui/__init__.py:126-150; all workspaces if it did not resolve); the `'*'` cookie selects all workspaces; a uuid cookie selects that workspace.
- **Measured on the migrated live copy** (`proto/files/live-copy.db` against `live-copy.pre-apply-backup.db`, both queried read-only):

  | View | Today (type_id join) | After |
  |---|---|---|
  | `'*'` cookie: all workspaces, archived included | 534 | 529 |
  | `'*'` cookie: all workspaces, archived hidden | 366 | 366 |
  | pedantic-drip `69696982…`, archived included / hidden; the hidden view is also the no-cookie board of a UI started in pedantic-drip's checkout | 397 / 240 | 397 / 240 |
  | terry_agent `f7b49c1d…`, archived included / hidden | 54 / 45 | 49 / 45 |

  The five extra rows today are pedantic-drip's rows for the five shared type_ids, joined a second time to terry_agent's archived namesakes. On a live copy today, a UI started in pedantic-drip's checkout shows 240 card links with no cookie and 366 with the `'*'` cookie (premortem `probes/ui_default_scope.out`).

**W3.2: links by uuid.**
- **Templates:** each link uses the entity uuid.
  - `_card.html:1` links `/entities/{{ item.entity_uuid }}`;
  - `_entities_content.html:73` links `/entities/{{ entity.uuid }}`;
  - `entity_detail.html:83` and `:98` link `{{ a.uuid }}` and `{{ c.uuid }}`.
- **Orphan cards:** rev 2.1's "an orphan card keeps its type_id link" goes, because pd can no longer create an orphan row (section 4.2).
- **The detail route** (`ui/routes/entities.py:160-205`):
  - **The identifier:** a uuid resolves globally. A type_id resolves only in a workspace an explicit uuid cookie selects. With no cookie or the `'*'` cookie it answers the 404 page, since every rendered link is a uuid and the startup workspace is hidden state. The route checks the cookie itself, before any library call; it never uses `effective_workspace_uuid`'s startup fallback (ui/routes/helpers.py:65) for a type_id.
    - **Who still sends a type_id:** only a URL typed or saved by hand.
    - **What it gets:** the 404 page with no cookie or the `'*'` cookie, never another workspace's namesake; with a uuid cookie, that workspace's entity.
    - **Tests:** `test_type_id_url_answers_404_without_a_selected_workspace[no-cookie|star-cookie]`, on the shared-type_id fixture plus a type_id one workspace holds (the red case: on the base, that type_id answers 200), and `test_type_id_url_resolves_in_the_cookie_workspace[uuid-cookie]`, on the shared-type_id fixture.
  - **Lineage:** `get_lineage(entity["uuid"], …)`, so a shared type_id no longer answers `[]` (open question 19). `_strip_self_from_lineage` compares uuids.
  - **Workflow:** `get_workflow_phase(entity["uuid"])`, one keyed read in place of today's scan-and-match by type_id (:193-194).
- **The Entities page:** `_build_workflow_lookup` (:23-28) keys on `wp["entity_uuid"]`, and the page looks up `e["uuid"]` (:103-106).
- **The mermaid graph** (`ui/mermaid.py:38-85`):
  - nodes are keyed and clicked by `uuid`;
  - edges come from `parent_uuid`;
  - styles come from `kind`.

  Lineage rows are `entities` rows (`_lineage_up` selects `e.*`). They carry `uuid`, `parent_uuid` and `kind`, but not the `parent_type_id` and `entity_type` the graph reads today, so today it draws only the current entity's own parent edge.

**W3.3: writer guards.**
- **The `update_entity` re-attribution cascade** (:8773-8788) is deleted, not guarded. The row has no workspace to rewrite.
- **`append_phase_event`'s unscoped fallback** (:9823) is deleted. The entity is resolved once, by the naming rule (6.3).

**The rows rev 2.1 deferred with the re-key** (W3's list, design:380-389) are all closed:

| Deferred item | Closed by |
|---|---|
| `update_workflow_phase` | keyed by `entity_uuid` (6.3) |
| the step-5 projection | keyed by `entity_uuid` (6.3) |
| `delete_workflow_phase` | deleted |
| `resolve_ref`'s exact match | the naming rule |
| `scripts/fix_kanban_columns.py:28` | deleted (section 14) |
| the 39 unscoped `get_entity` reads | section 8 |

**W3's tests, restated:**
- **One card:** unchanged. It is now structural, since the join can't fan out.
- **The card link works:** the link is the uuid, and it answers 200 with the owner's entity.
- **Orphan scope:** replaced by the refusal test above.
- **Entities page:** each namesake shows its own status. Both can now have rows.
- **Cascade:** re-attributing A's entity writes no `workflow_phases` row (A's `updated_at` is unchanged), and B's row is unchanged.
- **Unchanged:** the `set_parent` and `update_entity` by-type_id tests, the by-uuid keep-green test and the unresolved test (W3.4).

## 8. Unscoped entity reads by type_id

**Ruling: all of them are scoped in this round, by the naming rule.** After the re-key, no production site reads an entity by a type_id without a workspace.
- **Why now:** rev 2.1 held these back only because a scoped read that found A's entity would then write B's type_id-keyed row (design:389). Under key A, a write reaches only the resolved entity's own row. That hazard is gone, and I1's correction 1 needs both halves (1.1).
- **The sites:**
  - the 34 surviving `get_entity` call lines (inventory 6.1);
  - the 40 always-unscoped rows (inventory 6.2);
  - the 15 sometimes-unscoped rows (inventory 6.3).

  The inventory rows' own lines are at `77f06efb`; the file:line citations in the table's Change column are at develop `c1bbfae0`. Each RK task re-anchors its rows by symbol (open question 25).
- **The library rows** change by the rule itself (6.1, 6.3). Every other row passes a workspace its caller already has, or, for the CLIs, resolves one once from its project root, and skips when that fails (the CLIs' row).

| Group | Inventory rows | Where the workspace comes from | Change |
|---|---|---|---|
| **Library resolvers** | schema-50, schema-52, schema-54, schema-56, schema-57, schema-58, synth-1, schema-44, schema-29, schema-32 | the caller | the naming rule (6.1); the per-method changes in 6.3 |
| **Workflow server tools** | MCPW-1, -5, -7, -11, -14, -15, -21, -22, -23, -25, -30, -32, -41, -42 | `_require_workspace()` (W4.1) | each `get_entity` or `resolve_ref` in a handler passes `workspace_uuid=_require_workspace()`. For example, `get_mini_spec`'s event read (:2347) becomes a read of that entity's events |
| **Entity server tools** | MCPE-4, -7, -8, -9, -12, -14, -16, synth-2 | `_require_workspace()`, through `_resolve_ref_param` (W3.4) | after `_resolve_ref_param`, reads go by the resolved uuid; direct `get_entity` reads (entity_server.py:424, :493, :1061, :1335 at 4a6373f0) pass the workspace |
| **Engines the servers call** | engines-10, -24, -28, -33, -36, -38, -41, -42, -54, -57 | the `workspace_uuid` the engine method receives | the engines already take a workspace per call on their write paths (engine.py:129, :180; `list_by_phase`/`list_by_status` :271, :310). The read paths gain it: `get_state`, `feature_lifecycle`'s `get_entity` reads (:155, :258, :593), `promote_task` (it holds `task_workspace_uuid`), `check_workflow_drift` (`reconcile_check`'s workspace) and `router`'s `init_entity_workflow`/`transition_entity_phase`. **The contract:** an engine method that takes a type_id also takes `workspace_uuid`, and passes it to every library call it makes. `WorkspaceRequiredError` propagates through every engine, helper and MCP handler: no caller turns it into None, `[]`, not found or a skipped step. The engines catch only `sqlite3.Error` for their `.meta.json` fallback (`get_state`, engine.py:93-120), so a missing workspace is never answered from a file. Callers that swallow a `ValueError` today, for example `_validate_feature_type_id`, which relabels it `feature_not_found` (feature_lifecycle.py:134-135), and `_read_single_meta_json`, which answers None (reconciliation.py:211-212), are converted by RK4's strict flip, each with a real-database test (section 10). Before RK4, the global-unique fallback still answers |
| **Dark engine paths** | engines-13, -14, -15, -16 | the uuid already in hand | `EntityWorkflowEngine.get_state` and `abandon_entity`/`_abandon_descendants` hold the entity's uuid and drop it for the type_id (inventory `key_used`). They pass the uuid |
| **server_helpers** | engines-73, -76, -78; engines-74, -75, -77 | the entity server's workspace | `_process_register_entity`'s reads and the lineage helper (:484) pass it. **The `parent_type_id` branch (engines-74, -75, -77) is deleted:** its only production caller passes `None` for `parent_type_id` (entity_server.py:703) |
| **CLIs and the session-start orchestrator** | engines-80, -81, -82, -61, -87 | the CLIs: the project root, resolved read-only as ui/__init__.py:126-150 does: `ENTITY_WORKSPACE_UUID`, then the project's `workspace.json`, then `_lookup_workspace_uuid_by_project_root` on a `mode=ro` connection with `_repository_root(cwd)`. Never `resolve_startup_workspace_uuid` or `resolve_workspace_uuid` (project_identity.py:698, :739-740), which mint. The orchestrator: its already-resolved `workspace_uuid`, in `_sync_brainstorm_entities` (entity_status.py:107), with `_workspace_holds` (:228-241, scoped) and 1C's `_another_workspace_holds` (:244-257, unscoped; RK2 deletes it, 6.1) | `frontmatter_inject.py` (argv at :123-131), `frontmatter_sync_cli.py` with `frontmatter_sync`'s single-feature and backfill paths (`backfill_headers` lists only the resolved workspace's features), and the `secretary_intelligence parent-context` CLI resolve the workspace once. With no workspace, each warns on stderr, exits 0 and writes nothing. What a user loses: that run's effect for that feature (the injected frontmatter, the synced field, the parent-context line); nothing is written to another workspace. With the workspace unresolved, the orchestrator's brainstorm sync raises at the first file that needs registration once RK2 removes 1C's skip, and the orchestrator records it (entity_status.py:169-170); no read is unscoped |
| **UI** | UI-3, UI-5, UI-6, UI-7, UI-9, UI-10 | uuids; else `effective_workspace_uuid(request)` | W3.2 restated (section 7) |
| **Markdown** | MD-17, MD-24 | the MCP server | no change: tool parameters are unchanged (6.5) |

- **The entry-point table** (RK1 writes it, in both halves' briefs): for every engine, helper and MCP handler that names an entity, whether its caller passes the workspace or the function derives it, and from what. The codemod's method list (6.4) adds every entry point that takes it.
- **Sites Phase 1 deleted stay deleted:** engine.py:599 (engines-7) and entity_status.py:77 (engines-85), both cited at `4a6373f0`. That is why 34 of the 36 type_id lines survive (inventory 6.1).
- **Unscoped entity writes by type_id close the same way:**
  - `set_archived`, `set_deleted`, `update_entity` and `delete_entity` (6.3);
  - `cleanup_backlog.py`'s archive (SCR-3), which resolves its workspace before its archive loop, archives nothing when that fails, and passes it;
  - the doctor's `_fix_self_referential_parent` (engines-93), whose check already holds the offending uuid (inventory `rekey_needs`) and writes by it.

## 9. Rulings on the 27 open questions (inventory section 9)

| # | Question (short) | Ruling | Where |
|---|---|---|---|
| 1 | W1.2 passes a uuid to the type_id-keyed `set_archived` | `set_archived` follows the naming rule: a uuid names the entity in any workspace, and it writes `WHERE uuid = ?`. W1.2's call works as written: 1B landed it with a by-uuid branch in `set_archived` (database.py:8466-8471), and `set_deleted` gains the same path in RK1 | 6.3 |
| 2 | Is `workflow_phases.workspace_uuid` immutable? | The question goes away: the column is dropped, and the workspace is the entity's, read by join. The `update_entity` cascade that rewrote it is deleted | 4.2, 6.3, 7 |
| 3 | Which identity does criterion 6 mean? | The entity uuid, the identity of `events` and the three views. Key A holds whether or not `type_id` stays unique per workspace (schema_v2.py:64, FR-4) | 2.2, 2.4 |
| 4 | How is a type_id rename shown? | By a raw-SQL rename test: after W5.1 no API renames a type_id, but the key must survive one. The test renames `entities.type_id`, reads the row and the events by the new type_id and workspace, and checks the old type_id is not found. No `workflow_phases` write happens | 10 |
| 5 | Which key does the MCP boundary take? | The workspace uuid from `_require_workspace()`, in both servers. The legacy label only filters list and export tools | 6.5 |
| 6 | Where do markdown callers get a uuid? | They don't need one: tools keep their type_id parameters, and the server supplies the workspace. Decomposing's `parent_uuid` path keeps working, since uuids are global | 6.5 |
| 7 | Keep the list tools' all-workspaces fallback? | Recommended: no. With `project_id` omitted, `list_features_by_phase`, `list_features_by_status` and `query_ready_tasks` call `_require_workspace()`; `'*'` and a legacy id keep their meanings. Today, with the workspace unresolved, they list other workspaces' type_ids that the same server then refuses to act on. This would supersede W4.1's "Read tools keep today's behaviour" for these three, which the D3 ruling does not cover, so it is for the user (Q3). Without a ruling, the playbook keeps W4.1's text for them | 6.5, 12; Q3 |
| 8 | Does `phase_events` gain the entity key this round? | Yes: a nullable `entity_uuid`, required on new live rows | 3 |
| 9 | How are old events mapped? | The sole-holder and label-decided classes are attributed; the undecided (13) and no-holder (12) classes stay NULL and are kept verbatim. They are not marked: a NULL `entity_uuid` is the mark | 3.3, 5.2 |
| 10 | Avoid `project_id` as a workspace key? | Yes. It becomes a write-time label, never filtered on. `query_phase_events`' workspace scope joins through the entity, and the guard flags any `project_id` predicate on `phase_events` | 3.2, 6.3, 11 |
| 11 | Which `entity_axis_state` text? | views.py's `_VIEWS_DDL` (`WHERE event_type != 'skipped'`). The migration re-creates the view where the text differs, and R2 corrects v2 migration 3's docstring | 4.3 |
| 12 | Is `rebuild_tool` still a v1→v2 path? | Yes, for v1 sources at the target shape (version 26). It refuses a source whose `workflow_phases` has no `entity_uuid`, with the message "this file is not re-keyed. Make a copy with the prescribed backup command and migrate the copy, or use scripts/rekey_live_registry.py. Never open the source itself." Opening the source would migrate it with no backup (13.1), or turn the only pre-rekey backup into version 8. A test checks that the message names the tool and that the source stays byte-identical. Its copy lists (wp, pe) and `_preimport_vocab_diff` follow the new shape, and its re-mint maps both tables' `entity_uuid` through its old-to-new uuid map (section 14). The staging build already reaches v2/8 through both chains (4.1) | 14, 15 |
| 13 | Old processes lose write access after a live bump | Planned for: the C23 guard makes an old build read-only on the version-8 file, and its type_id SQL fails loudly. The operator manual closes every pd process first, publishes the new build right after, and treats a leftover old process as a restart | 13 |
| 14 | Should rows no entity holds stay representable? | No. A foreign key plus `wp_reject_unknown_entity` refuse them, and no pd code hard-deletes an entity. The tolerating code goes: the `OR e.uuid IS NULL` clauses and the doctor's orphan fix (engines-92). The doctor's orphan check (engines-91) stays, re-keyed, to report a row that a raw-SQL delete with foreign keys off can leave (4.2). In the 10 test files that insert orphan rows, a case that needs a row registers its entity first. A case that only tests orphan tolerance is deleted with the code it tests: the `_insert_orphan_workflow_row` cases of tests-38, -39 and -40, and C8's orphan `db_only` branch in `reconciliation.py`, if W1 leaves it. RK2's implementer checks that on the landed Phase 1 code before editing, and records it | 4.2, 14, 15 |
| 15 | Rows of archived or soft-deleted entities | They stay with their entity, as the archived and soft-deleted classes; archiving and soft delete are flags. The board hides archived rows as today. `delete_entity`'s docstring is corrected | 5.1, 6.3 |
| 16 | Dark and test-only sites | Re-keyed like live code, because the guard has no exemption for dark code. Sites that hold a uuid use it (engines-13 to -16). The unreachable `parent_type_id` branch in server_helpers is deleted (engines-74, -75, -77). `display.rename_entity` goes with W5.1. The 5D and task paths (engines-17 to -21) take the workspace like any engine path | 8, 14 |
| 17 | `cleanup_backlog.py` and `pd_state_diff.py` | Both in scope: cleanup_backlog passes its workspace (SCR-3, RK1); pd_state_diff joins and replays by `entity_uuid` (SCR-1, SCR-2, RK2). pd_state_diff opens its file read-only and fails soft, so it can never migrate the live file | 14 |
| 18 | `migrate_db.py merge-entities` and the C22 script | merge-entities has been broken since migration 11: on a fresh v25 file it stops with `no such column: main.entities.parent_type_id` and writes nothing (`work/merge_probe/merge.out`). **For the user** (Q4): delete it (recommended), or keep it. The C22 script is a one-off that has already run; after the re-key its SQL can't run on any current file, so it is deleted with its tests | 14; for the user |
| 19 | The UI's lineage and mermaid | W3.2 restated: lineage by uuid, and mermaid nodes by uuid, edges from `parent_uuid` and styles from `kind`. This fixes the `[]` lineage for a shared type_id and the missing edges | 7 |
| 20 | What must the criterion-4 guard cover? | The four existing roots plus `ui/routes`, `ui/mermaid.py` and repo `scripts/`. It checks split SQL at the function level, type_id-keyed Python maps and comparisons over workflow rows, template links, the API's shape and the schema | 11 |
| 21 | Pinned-schema tests | A test that opens `EntityDatabase` (the head chain) pins the head shape and is updated in place: `test_type_id_is_primary_key` becomes an `entity_uuid` test, the 8 columns become 7, and the trigger and index names change. A test that stops the chain at version N keeps pinning N | 15 |
| 22 | No pre-migration builder | Add `test_helpers.make_pre_rekey_db(path, generation)`. It builds a file with the re-key entries left out of the two registries (patched copies of `MIGRATIONS` and `V2_MIGRATIONS`, and `V2_SCHEMA_VERSION` 7): generation `v1` gives the fresh chain at 25, and `v2` gives a staging build at 7. A seeding helper adds the section 5 classes by raw SQL on the old shape, as the prototype's class fixture did | 10, 15 |
| 23 | Phase-1 effects the design doesn't name (inventory 7.3) | Phase 1's own plan absorbs them, since they land before Phase R. The test list is re-derived from the landed Phase 1 code: by R2 if Phase 1 has landed when R2 is written, otherwise by each RK task at its start (question 25) | 15 |
| 24 | Test breakage was determined statically | R3's code verification runs G1–G5 on a scratch export with the playbook's changes. This design's prototype ran the migration and its checks, and no test suite | 13.5 |
| 25 | Line drift after Phase 1 | Re-anchor by symbol, with no second R0: row ids and symbols are stable, and every row names its symbol. Each RK task does it on its own branch before editing (plan:72), since R2 may be written before Phase 1 lands | 15 |
| 26 | Inclusion boundary | Keep the rows (engines-11 to -13, -46, -65, -89, -90, -94; synth-1, -2). As feeders they are the checklist for the call-site edits | 15 |
| 27 | "Deciding line" for unchanged rows | Acceptable for R0. For Phase R, each surviving row's decision is its task in section 15, which supersedes the deferral quote | 15 |


**For the user.** R3's revision turns the open items into seven questions, asked in two batches through AskUserQuestion, at most four at a time (playbook §0.4). Each first option is the recommendation, and the playbook follows it unless the user rules otherwise. Q3 is the exception: no ruling covers it yet, so without an answer the playbook keeps today's fallback. Section 15's prerequisites table says what each answer gates.

**Batch 1: after this revision is applied, before R4 starts.**

1. **Q1: will the user hold the sitting this round, and does pd stay disabled until it?** Phase R's code (13 tasks; about 1,800 test call sites and 115 production calls change, 6.4) pays off only at the live sitting.
   - **Hold it this round; pd stays off (recommended).** Cost: no pd in any session until the sitting, as since 2026-09-24. R4 starts once 2A and 2C land, and no session can publish Phase R code or migrate the live file by accident (13.1).
   - **Hold it this round; re-enable pd now.** Cost: every agent command runs under the temp-HOME rule, and the migration's live-path tripwire is the only backstop (13.1). A pd session started in a Phase R clone republishes that clone, and pd then stops starting (the tripwire refuses) until develop is re-published.
   - **Not this round: stop after R3.** Problem 1 (the board and links) and the type_id-only updates stay open, and 1C's skip stays. R4 does not start. This design and the playbook are kept as the record, the deferral goes into the Deferred table (section 14), and the plan's Done-when deferral clause applies (section 12, item 8).
   - **Blocks:** R4's start (R4-A and R4-C0, and so every task).
2. **Q2: must every call that names an entity by type_id pass a workspace, for good (the strict rule, 6.1)?**
   - **Strict (recommended).** Criterion 4 asks for enforcement by the API's shape (plan:283). Python can't make `workspace_uuid` required only when the value passed is a type_id, so the shape is enforced where every method resolves: `_resolve_identifier` refuses a type_id with no workspace (6.1). The plan's words don't require a run-time refusal; this is the design's reading of them.
     - **Cost, measured at `ddc299a0` (6.4):** under the full rule, 1451 tests fail before any task's edits, 961 of them the codemod's. There are 1057 direct and 754 entry-point test call sites, 343 engine/helper and 250 MCP-handler sites among them beyond the codemod's list, and about 115 production calls.
     - **Lasting:** every future test and caller passes a workspace or a uuid; each rebase while the sitting waits re-runs the codemod; read tools answer `workspace_unresolved` in a session with no workspace.
     - **Consequence:** R4-F1 to R4-F4 run, and criterion 4 is enforced by the API's shape.
   - **A default workspace bound to each `EntityDatabase` connection.** Few calls change, but it is hidden state. A process that serves several workspaces (the UI server, one workspace per request), or a test session whose fixtures register several on one connection, would resolve in whatever workspace was bound last, so criterion 4 would hold only by discipline. R4-F is then re-planned (a binding API in place of the four slices), and 6.1 is revised and re-reviewed.
   - **Blocks:** R4-F1 to R4-F4; if still open, it must be answered before R4-F1 is cut. R4-A to R4-E are needed under either option.
3. **Q3: the three list tools' default (open question 7).** With `project_id` omitted and no resolved workspace, do `list_features_by_phase`, `list_features_by_status` and `query_ready_tasks` refuse, or keep listing every workspace?
   - **Refuse with `workspace_unresolved` (recommended).** A session with no resolved workspace gets an error instead of a cross-workspace list; `project_id='*'` still lists every workspace (6.5). R4-B scopes them to `_require_workspace()`, with two tests. This supersedes W4.1's "Read tools keep today's behaviour" for these three, which the D3 ruling does not cover (section 12).
   - **Keep today's fallback.** These three stay the one read path that answers across workspaces when the workspace is unresolved. R4-B leaves them, and W4.1's text stands.
   - **Blocks:** R4-B's change 2 only; if still open, it must be answered before R4-B starts. A yes that arrives after R4-B merged moves the change to R4-F4. Without an answer, today's fallback stays.
4. **Q4: delete `scripts/migrate_db.py merge-entities`, or keep it?** `migrate.sh import` runs it; it has been broken since migration 11, and it writes nothing (question 18).
   - **Delete it (recommended),** as the repo's no-backward-compatibility rule asks. Cost: if a cross-machine import's entity merge is ever needed, it is rebuilt per entity. R4-E deletes `cmd_merge_entities`, its subparser, `TestMergeEntities`, `test_migrate_deepened.py`'s merge tests and `migrate.sh import`'s merge step, which becomes a loud refusal counted in `import_failures`. The guard's declared entries fall to 0 once 4A lands (section 11).
   - **Keep it as is.** A broken subcommand stays. Its declared guard entry is keyed by function plus a sha256 of its source, so any edit to it turns the guard red. The high-water mark stays 1 after 4A, and its Deferred row stays (section 14).
   - **Blocks:** R4-E's deletion part and R4-G's declared-entry set; if still open, it must be answered before R4-E starts.

**Batch 1 answered (user, 2026-09-26):**
- **Q1:** the user asked, verbatim, "since pd is off, isn't it a good time to fully re-key with any side effect?". The orchestrator read it as option 1 (hold the sitting this round; pd stays off) and told the user so. The live migration itself still waits for Q5's yes.
- **Q2:** "Strict (Recommended)".
- **Q3:** "Refuse (Recommended)".
- **Q4:** "Delete it (Recommended)".

**Batch 2: when Phase R's integration (playbook 1.12) has passed and R4-I (RK6) is next.**

5. **Q5: the live migration itself (RK6), as F3 says: migrate the live registry, verify, land Phase R on develop and publish, in one sitting with pd disabled in every Claude Code session, the operator's included (13.1, 13.3)?** It is one question with one yes.
   - **Yes, run the sitting (recommended).** Cost: pd is off in every session for the sitting, while the operator runs the playbook's S1–S12. The live file goes from v2/7 to v2/8, develop and the cache hold Phase R, and a rollback follows 13.4 (playbook 3.5). The fingerprint the sitting records becomes F1's baseline (section 12, item 10).
   - **Defer.** Phase R stays on its branch, so develop and every publish stay on version-7 code, and pd works as it does after Phase 1. Phase R rebases and re-runs its integration QA and per-rebase checklist at every landing on develop (plan:75-76; section 15); there is no deadline. Problem 1 and the board and link fixes (W3.1–W3.3) wait with it. While deferred, brainstorm files whose type_id another workspace holds stay unregistered in the new workspace, named in every session start's warnings (1C's skip). The Deferred rows stand, and the Done-when deferral clause applies.
   - **Blocks:** R4-I (the sitting) and the sitting's plan changes (section 12, items 9–10).
6. **Q6: what should happen to pedantic-drip's five namesakes** (5.3)? They are not archived and show on its board (two promoted brainstorms, and features 002–004, completed at finish); terry_agent holds all five archived, and their artifacts exist only in `/Users/terry_agent/docs`.
   - **No change this round (recommended).** pedantic-drip's board keeps them. The migration keeps today's attachment, and the Deferred row stays.
   - **Archive pedantic-drip's five copies.** A gated live write after the sitting (`set_archived` by uuid, reversible), with its own fingerprint check. They leave pedantic-drip's default board; terry_agent's copies are untouched.
   - **Merge into terry_agent's copies.** Its own procedure after the sitting: copy the row state into terry_agent's backfill-seeded rows, optionally repair the 13 undecided events once, then archive or soft-delete pedantic-drip's copies. A gated live write. One entity per type_id then carries the history.
   - **Not an option:** re-attributing them to terry_agent. `UNIQUE(workspace_uuid, type_id)` refuses it, since terry_agent already holds all five.
   - **Blocks:** nothing in R4. The first option is recorded in the Deferred table; the other two are scheduled after the sitting's last step, as their own gated write.
7. **Q7: after the sitting, what becomes of `scripts/rekey_live_registry.py`,** whose `apply` and `restore --confirm-live` write the live file?
   - **Delete it after F2 (recommended),** by this design's one-off rule (section 14): F2's commit removes the tool and its tests. A restore after F2 follows the playbook's 3.5 written steps with plain `sqlite3`.
   - **Keep it.** A permanent script that can write the live file, kept behind `--confirm-live` and the live-path guard, with its reason recorded in section 14. Its `restore` and `diff` subcommands stay available.
   - **Blocks:** F2's cleanup commit only.

## 10. The future-proof criteria, and what shows each

- **Two kinds of evidence:**
  - **"Prototype" keys** are results already recorded in `work/proto/proto-results.json`.
  - **Tests** are the red-first tests R4 writes. The playbook (R2) owns their final names.
- **Where the tests live** (G1 collects them all):
  - `plugins/pd/hooks/lib/entity_registry/test_rekey_schema.py`: the schema tests of criteria 1 and 3;
  - `plugins/pd/hooks/lib/entity_registry/test_rekey_migration.py`: criterion 5's tests, and `test_rows_join_entity_phase_status_one_to_one`;
  - `plugins/pd/hooks/lib/entity_registry/test_rekey_identity.py`: the behaviour tests of criteria 1, 2 and 3;
  - `plugins/pd/hooks/lib/entity_registry/test_naming_rule.py`: criterion 4's refusal and resolution tests;
  - `plugins/pd/mcp/test_rekey_event_streams.py`: `test_mini_spec_of_a_is_invisible_to_b`;
  - `plugins/pd/ui/tests/`: W3's restated tests (RK3);
  - the guard: `plugins/pd/hooks/lib/doctor/test_entity_keyed_access.py` (section 11).
- **Red first, or keep-green:** each test below is red on RK1's head for a behavioural reason, except those marked keep-green. Those already hold today and guard the new key against regression (the review protocol's keep-green mark, plan:97).

| Criterion | Design element | Shown by |
|---|---|---|
| **1. One row per entity, schema-enforced** | `entity_uuid` PRIMARY KEY with a foreign key to `entities(uuid)`; `wp_reject_unknown_entity`; `enforce_immutable_wp_entity_uuid` | **Prototype:** `guard_insert_duplicate_entity` (refused, UNIQUE), `guard_insert_unknown_entity`, `guard_move_row_to_other_entity`, and `second_row_same_type_id` = 2 on the live copy. **Tests:** `test_rekey_schema.py::test_primary_key_is_entity_uuid`; `test_two_namesakes_two_rows_and_no_cross_write`; `test_upsert_writes_own_row_leaves_namesake_unchanged` (today it refuses). **R3:** rehearsal query Q-keys |
| **2. Survives every identity change** | The key is the one identity column `entities` makes immutable (`enforce_immutable_uuid`, present on the live copy). No identity is stored beside it | **Tests:** `test_row_and_events_survive_type_id_rename` (raw-SQL rename, open question 4); `test_row_survives_reattribution[<writer>]`, one case per re-attributing writer: `update_entity`, `backfill_project_ids` and `claim_unknown_entities` (no `workflow_phases` write happens: `updated_at` is unchanged); `test_shared_type_id_rows_are_independent`; and, keep-green because today's type_id key already survives these three, `test_row_survives_reparent`, `test_row_survives_archive_round_trip` and `test_row_survives_soft_delete_round_trip`; and the rebuild's re-mint, which maps both keys through its old-to-new uuid map (`test_rebuild_rekey.py`). **Prototype:** `guard_hard_delete_entity_with_row` (a hard delete fails loudly) |
| **3. No identity copy drifts silently** | No copy left in `workflow_phases`. The row view derives `type_id` and `workspace_uuid` at query time. `phase_events.type_id`/`project_id` are write-time labels of a history whose labels are never rewritten (3.2), never keys (the guard enforces this) | **Tests:** `test_rekey_schema.py::test_no_identity_copy_columns`; `test_row_view_reads_current_identity` (after a raw rename and a re-attribution, `get_workflow_phase` returns the new values). **Guard:** rule 1's `project_id` clause, and rule 6: no production code compares a `query_phase_events` row's `type_id` label with an entity's current type_id (3.2) |
| **4. No path reaches another workspace's row by type_id** | Structural: `workflow_phases` has no `type_id`. API: the naming rule (6.1). Test: the guard (section 11) | **Guard:** `test_entity_keyed_access.py`, which detects 34 sites at `4a6373f0` (25 SQL functions, 5 Python sites and 4 template links) and must detect none outside its declared inventory after RK5. Its rules resolve f-string, `%` and `.format` operands, and its self-tests replay R3's mutations (section 11). **Tests:** `test_naming_rule.py::test_type_id_without_workspace_raises[<each ENTITY_NAMING_METHODS pair>]`; `test_type_id_resolves_only_in_callers_workspace[...]`; `test_uuid_resolves_its_entity_whatever_the_workspace[<pair>]` (red on base for five pairs, keep-green for ten; 6.1); `test_refusal_reaches_the_caller[<site>]`, one real-database case per caller that swallows the refusal today (section 8); `test_mini_spec_of_a_is_invisible_to_b` (the 1.2 bar's item 3: events per entity); W3's restated tests (section 7) |
| **5. One target schema, resumable copy-rename** | One function on both chains (`V2_MIGRATIONS[8]`, `MIGRATIONS[26]`); probe, foreign keys off and verified, `BEGIN IMMEDIATE`, re-probe, audit, copy, count check, `foreign_key_check`, `COMMIT`; forward-only; rollback by restore | **Prototype:** `target_schema_identical` (all four files true); `views_identical_live_vs_staging`; `injected_failure_*`; `killed_process.*`; `crash_before_stamp_resume.*`; `reopen_no_change.*`; `rollback_sha256_matches_backup`. **Tests:** `test_rekey_migration.py::test_fresh_and_staging_shapes_identical`, `test_rolls_back_on_injected_failure`, `test_resumes_after_crash_before_stamp`, `test_reopen_is_a_no_op`, `test_audits_reattached_dropped_and_stale_rows` (class fixture), `test_foreign_keys_restored`, all on `make_pre_rekey_db` files; `test_two_runners_on_a_pre_rekey_v2_file_migrate_once`, with 4C's race tests green with migration 26 registered (4.4); `test_live_path_refuses_without_the_operator_flag[<case>]`, whose cases are the refusal, the operator flag set, a copy and a fresh file (13.1). **R3:** the rehearsal (13.5) |
| **6. Fits the v2 direction** | The key is the key of `events` and of the three views. `phase_events` gains the same key, so a later fold into `events` maps rows directly | **Measured:** on the migrated live copy, 529 of 529 rows join `entity_phase_status` on `entity_uuid`, at most one match each. **Test:** `test_rows_join_entity_phase_status_one_to_one` on a staging file. **Recorded, not fixed:** `update_workflow_phase` and `upsert_workflow_phase` emit no v2 event (inventory O1); a Deferred row (section 14) |
| **7. Consistent with rev 2.1** | The naming rule restates W2.1, W3.4 and D5 (6.1); W3.1–W3.3 are restated (section 7); nothing re-adds a W1 deletion | **Tests:** feature 129's four cross-workspace tests keep their assertions (D5), with two library calls among them passing uuids instead of type_ids (section 12); W2.1's "explicit workspace" and "upsert" tests, restated (section 12); W3.4's tests unchanged. **1B's and 1C's tests keep their assertions:** 1B's `test_session_start_reads_no_files.py`, `test_get_state_without_hydration.py`, `test_reconcile_status_scoped.py` and `test_update_entity_archived.py`, and 1C's `test_brainstorm_registration_scoped.py` (except the skip tests RK2 rewrites), gain only `workspace_uuid=` or uuid arguments; each codemod slice's reviewer checks that against the diff. **Guard (secondary):** its inventory holds no function W1 deletes |

## 11. The criterion-4 guard test

- **The file:** `plugins/pd/hooks/lib/doctor/test_entity_keyed_access.py`, beside `test_audit_writes.py`. G1 collects it.
- **Its model:** the identity-inference inventory in `test_audit_writes.py` (:498-650, unchanged since `4a6373f0`):
  - an AST scan over declared roots;
  - a declared inventory that the detected set must **equal**;
  - a high-water mark that may only fall (`_INVENTORY_HIGH_WATER`, :628). Its comment keeps the rule: raising it "is a deliberate act with a line in that table, not a way to quiet a red test".

**Scan roots** (open question 20):
- **Today's inference roots:** `plugins/pd/hooks/lib`, `plugins/pd/mcp`, `plugins/pd/ui/templates` and `plugins/pd/scripts` (`_INFERENCE_SCAN_ROOTS`, :498-509).
- **Added:** all of `plugins/pd/ui` (`routes/*.py` and `mermaid.py`) and the repo's `scripts/` (`migrate_db.py` and the other repo scripts).
- **Skipped:**
  - test files: `test_*.py`, `conftest.py` and any `tests/` directory;
  - `.venv` and `__pycache__`;
  - docstrings.

**What it flags.** Each rule yields `(relative path, enclosing function, rule)`. Sites are keyed by function, not line, so ordinary edits don't churn the inventory.
1. **SQL in one string.** Adjacent literals, `+` chains and f-string constant parts are joined, as `work/scan/sql_literals.py` does, and the operands of f-strings, `%` and `.format` are first resolved to every string constant they can take in the function. So 1B's `set_archived`, whose `f"WHERE {key_column} = ?"` (database.py:8471) slipped past the literal-only join, is caught. The rule flags a string that:
   - names `workflow_phases`, `phase_events` or `entities`, and has a SQL verb;
   - has a `type_id` predicate (`=`, `IN`, `LIKE`, `GLOB`, `IS`, `>=`, `<`, `BETWEEN`, or a function call on the column, on either side);
   - has no unconditional `workspace_uuid` predicate: one under `IS NULL OR`, or appended under an `if`, does not count.

   It also flags a `project_id` predicate on `phase_events`.
   - **Labels:** in a string that names `phase_events`, it flags any predicate on that table's `type_id` or `project_id` (unqualified, or qualified by `phase_events` or its alias), whatever else the string holds. The labels are never keys, even beside a workspace predicate on `entities`.
   - **Why a type_id predicate always needs a workspace predicate:** after the re-key, a type_id predicate names an entity. All-workspaces lists and searches filter on other columns (kind, status, phase, an FTS `MATCH`). The probe found no legal all-workspaces SQL with a type_id predicate outside the declared entries (`guard/guard_probe_hits.json`), once `feature_entity_id` is scoped (6.3).
2. **SQL split across literals.** In one function:
   - a literal holds such a predicate but names no table;
   - another literal names one of the three tables;
   - no literal anywhere in the function holds an unconditional workspace predicate.

   This is the shape of `query_phase_events`' `conditions.append("type_id = ?")` (database.py:9854).
3. **Python maps and comparisons over workflow rows.** It applies in a function that calls `list_workflow_phases`, `get_workflow_phase`, `query_phase_events` or `query_phase_events_bulk`. It flags a row's `x["type_id"]` or `x.get("type_id")` used as a dict-comprehension key, a set-comprehension element, a comparison or membership operand, a subscript key, the first argument of a mapping's `get`, `setdefault` or `pop`, or inside a `key=` lambda. Workflow rows are matched by `entity_uuid`.
   - **Measured:** the extended probe finds the same five functions as the first (`calvin/guard_rule3_extended.out`).
   - **Its limit:** it is function-local. A helper that receives rows from its caller is the reviewer's to check.
4. **Entity links:** `/entities/{{ … type_id }}` anywhere in `ui/templates`, and any Python f-string under `plugins/pd/ui` that builds an `/entities/` link from anything but a uuid, such as `ui/mermaid.py:67`'s `/entities/{safe_tid}`, a type_id.
5. **The API's shape and the schema.** These run on a temp `EntityDatabase` (`tmp_path`, with `ENTITY_DB_PATH` unset):
   - **The method list:** `ENTITY_NAMING_METHODS`, a declared tuple of (method, parameter) pairs, must equal the pairs an AST scan of database.py finds: every parameter of a public `EntityDatabase` method whose name matches `(^|_)type_ids?$`, `_type_id$`, `(^|_)ref$` or `prefix`, so `type_ids`, `feature_type_id` and `entity_ref` count too. With the old names (`ref`, `type_id`, `parent_type_id`, `prefix`) the scan finds 21 pairs at `4a6373f0`; with `delete_workflow_phase` deleted, 20 (6.3). The patterns also match two parameters outside the 20 (premortem `probes/method_params-5cc2ab75.out`): `query_phase_events_bulk.type_ids`, which RK2 turns into `entity_uuids` (6.3), and `refuse_deleted_or_cross_workspace_parent.child_ref`, which names the child only in an error message. The guard lists a parameter like that as an exclusion, with its reason. A new method that names an entity therefore can't skip the next check.
   - **The refusal:** each pair, called with a type_id in that parameter and no workspace, raises `WorkspaceRequiredError` (a `ValueError`) matching `needs a workspace_uuid`; the message names the parameter (6.1). `set_parent` is checked once per parameter, and `append_phase_event` with a `project_id` label but no `workspace_uuid`.
   - **The schema:**
     - `workflow_phases` has no `type_id`, `workspace_uuid` or `uuid` column, and its primary key is `entity_uuid`;
     - `phase_events` has `entity_uuid`;
     - no index on either table leads with `type_id` or `project_id`.
6. **The event label** (3.2): no production code compares the `type_id` key of `query_phase_events`' results with an entity's current type_id. Rule 3 already flags that inside the calling function; this check extends it to the helpers such rows reach.

- **Self-tests:** each of R3's mutations (premortem `probes/mut` and `probes/mutguard`: f-string and `.format` columns, conditional workspace appends, wider predicates, a Python-built link, unlisted parameter names) is a scanner self-test, red before the widened rules.
- **What it cannot see:** SQL built at run time from data, and SQL outside Python strings. With rule 3's function-local limit, those are the reviewer's to check.

**Allowed, and why:**

| Entry | Reason | Lifetime |
|---|---|---|
| Any function that is a value of `MIGRATIONS`, `MIGRATIONS_DOWN` or `V2_MIGRATIONS`, computed from the registries at test time rather than listed | They transform historical shapes and run only before the target shape exists. The new `_v2_migration_8_rekey_workflow_phases` reads the old columns by design, and keeps all its SQL inside itself: its tests inject failures through an SQL-free seam it calls between stages (`_rekey_fault_point(stage)`), so no helper outside the registries holds re-key SQL. The probe found 8 such functions with hits at `4a6373f0`, all in the registries | permanent |
| `scripts/migrate_db.py::cmd_merge_entities` | Broken since migration 11 (`work/merge_probe/merge.out`; question 18); it writes nothing. Listed only if the user keeps it (Q4, whose recommendation is to delete it). Keyed by the function name plus a sha256 of its source, so any edit to it turns the guard red | until it is fixed or deleted |
| `entity_registry/display.py::_rename` | W5.1 (task 4A) deletes it | until 4A has landed on develop. While Phase R waits, 4A cannot edit the guard, which exists only on `followups-phase-r`: Phase R's rebase fix-up removes the entry once 4A has landed. If 4A lands only after Phase R, 4A removes it |

- **High-water mark:** the count of declared entries: at most 1 while `display._rename` exists, if merge-entities is deleted (Q4's recommendation), or 2 if the user keeps it.
  - **`display._rename`'s entry goes** once 4A has landed: Phase R's rebase fix-up removes it and lowers the mark (the row above).
  - **Then** the mark is 0 with merge-entities deleted, or 1 if the user keeps it, until its Deferred row reopens.
- **Measured at `4a6373f0`.** Scripts in `work/guard/` ran over the `4a6373f0` export (output in `guard_sites_summary.out` and `guard_probe_py.out`):
  - rules 1 and 2 flag 34 functions: 8 in the migration registries, and 26 elsewhere;
  - of the 26, one is a docstring the probe did not skip (`parse_backlog_md.apply_records`), which leaves 25;
  - rule 3 flags 5 Python sites: `run_backfill`, `check_workflow_drift`, `WorkflowStateEngine.list_by_status`, `_build_workflow_lookup` and `entity_detail`;
  - rule 4 flags 4 template links;
  - **in all, 34 sites:** the 25 SQL functions, the 5 Python sites and the 4 template links.
- **The 34 sites at `4a6373f0`,** each with its task in section 15:
  - **Fixed by the naming rule and the new SQL (RK1, RK2):** the database.py methods of 6.3, `_fix_self_referential_parent`, `rebuild_tool._preimport_vocab_diff` and pd_state_diff's two functions;
  - **Deleted:** `delete_workflow_phase`, `_fix_remove_orphan_workflow`, the C22 script's two functions and `fix_kanban_columns.py`;
  - **Declared or deleted:** `display._rename` (declared until 4A's W5.1 deletion lands); `cmd_merge_entities` (deleted by R4-E if the user agrees, as Q4 recommends; declared if the user keeps it);
  - **Rule 3's five:** `run_backfill`, `check_workflow_drift` and `WorkflowStateEngine.list_by_status` in RK2; `_build_workflow_lookup` and `entity_detail` in RK3;
  - **Rule 4's four links (RK3):** `_card.html:1`, `_entities_content.html:73`, and `entity_detail.html:83` and `:98`.
- **Why the guard is not vacuous:** each rule has sites today that the re-key removes. After RK5, the detected set equals the declared inventory.

## 12. Consistency with design rev 2.1

**Kept as written:**
- **W1's deletions:** nothing here re-adds a deleted path. The sites W1 deletes are left out of section 8 (engines-7, engines-85), and the guard's inventory holds none of them.
- **1B's W1 as executed** (session start reads no files, cascade recovery by uuid, `set_archived` accepts a uuid, `reconcile_status` scoped): kept. Its four test files (`test_session_start_reads_no_files.py`, `test_get_state_without_hydration.py`, `test_reconcile_status_scoped.py`, `test_update_entity_archived.py`) are criterion 7's evidence: they gain only `workspace_uuid=` or uuid arguments, with their assertions unchanged (section 10).
- **1C's scoped brainstorm registration:** kept, except its skip of a type_id only another workspace holds (`_another_workspace_holds`, entity_status.py:244-257), which RK2 removes, rewriting its skip tests (6.1).
- **W2.2–W2.7:**
  - name-not-path;
  - activation seeding: W2.5's `create_workflow_phase` call inside `activate_feature` already passes the caller's workspace, which the naming rule requires anyway;
  - the backfill's scope (W2.6).
- **W3.4:** `_resolve_ref_param` resolves in the caller's workspace, and explicit uuids pass through.
  - **Feature 129's four tests keep their assertions,** as W3.4 and the plan require (plan:257).
  - **Two of their calls change, by hand, not by the codemod:** the `HANDLERS` lambda at `test_cross_workspace_matrix.py:230-236` and the call at `:307` both call the library's `set_parent` with a child and a parent type_id from two workspaces, so both pass the entities' uuids instead (D5), with the assertions unchanged. The entity_registry codemod slice (R4-F1) owns them.
  - **The other call the churn count flags** (`test_cross_workspace_mcp_regression.py:213`) already passes uuids, to the MCP tool (`calvin/feature129_codemod_touch.out`).
- **W4:** `_require_workspace()`. This design adds read tools to its callers.
- **D5:** an explicit uuid may point anywhere. This is the naming rule's uuid clause.

**Superseded.** The authority is the D3 ruling (plan:45-46; design:143-147). It supersedes the "Deferred" rows for the re-key, the read-scoping and the type_id-only writers, and it absorbs W3.1–W3.3. The rows below follow from it:
- **W2.1's column text, upsert refusal and row-column tests:** the columns, and the other workspace's row they speak of, no longer exist under the re-key. W2.1's call-site contract (a type_id plus the caller's workspace) is kept, as the naming rule.
- **W4.1's "Read tools keep today's behaviour", for read tools that name an entity:** their reads are the read-scoping row.
- **Not covered:** the three list tools' default (open question 7). It goes to the user (Q3, section 9); without a ruling, W4.1's text stands for them.

| Rev 2.1 text | Where | Replaced by |
|---|---|---|
| `create_workflow_phase`: "Omitted, the type_id must be globally unique" | W2.1 (design:278-280) | a type_id with no workspace raises (6.1) |
| "inserts the resolved entity's `type_id`, `workspace_uuid` and `uuid` explicitly, so the autofill trigger never guesses" | W2.1 | the row stores `entity_uuid`; the autofill trigger is dropped (4.2) |
| `upsert_workflow_phase` "refuses, rather than overwrites, a row that belongs to another workspace"; the test "Upsert refuses: … on B's row raises, and B's row is unchanged" | W2.1 and its tests | A's call writes A's own row, and B's row is unchanged. The test becomes `test_upsert_writes_own_row_leaves_namesake_unchanged` |
| "Every lane: … asserts the row, with its `workspace_uuid` and `uuid`"; "Explicit workspace: … stores `workspace_uuid == A` and the entity's `uuid`" | W2 tests | assert that `entity_uuid` is A's entity uuid, and that the row view's `workspace_uuid` is A |
| the board join, workspace filter, orphan clause and measured figure | W3.1 | section 7 |
| "An orphan card … keeps its type_id link" | W3.2 | deleted: pd can no longer create an orphan row (4.2) |
| the cascade guard and "raises on ambiguity" for the fallback | W3.3 | both code paths are deleted (section 7) |
| "Named, and deferred with the re-key (D3)" | W3 (design:380-389) | closed (section 7's table) |
| "Read tools keep today's behaviour" | W4.1 | read tools that name an entity call `_require_workspace()` (6.5); the three list tools do only if the user agrees (Q3, section 9) |
| Deferred rows "Re-key `workflow_phases` by entity uuid (D3)" and "Scope the 39 unscoped `get_entity` reads, and guard …" | Deferred table | closed by Phase R |

**Plan changes this design needs.** The playbook's §0.3 carries their texts, and the orchestrator applies each by its quoted text, re-anchored against develop when it applies it. Anchors are the plan at develop `c1bbfae0`.

*Apply now: one commit on develop, before R4 starts.*

1. **Landing (plan:75):** Phase R lands on develop only in the live-migration sitting, after the user's one yes (Q5). Until then it waits on `followups-phase-r`, under the rebase rule.
2. **Rebase rule (plan:76):** a phase that rebases onto develop after Phase R has landed adopts Phase R's naming rule and row view (section 6). Strict-rule failures in its own new tests are its own to fix.
3. **Shared files (plan:77-79):** `database.py`'s entry reads "Phase R re-keys `workflow_phases` and `phase_events`; 4A edits a docstring" in place of 2B's edits. Added: `backfill.py` and `engine.py` (Phase R; 4A's W5.7 deletions), `mcp/test_workflow_state_server.py` (Phase R; 4A deletes tests; 4C may edit fixtures), `mcp/test_create_feature_lanes.py` (Phase R; 4C's fixtures) and `hooks/sync-cache.sh` (3A; Phase R's publish guard, 13.2).
4. **R4's order (plan:316):** R4 starts once Phase 1, 2A **and 2C** have landed and the user has answered the first question batch (section 9). 2C (plan:251) edits `_resolve_ref_param` and the entity tools, which RK1 also edits. R4-C (RK2) also waits for 4C, and R4-F3 for 4A (section 15).
5. **F1, whenever the code under test holds Phase R** (Phase R's integration, and F2 after the sitting; F1 is plan:407-455):
   - **The baseline (setup step 2, plan:411):** after making snapshot S, open one copy of S with the code under test, which migrates it (the tripwire is inert on copies, 13.1), and fingerprint that copy as the baseline. Each step starts from a copy of the migrated S.
   - **The row fingerprint (plan:416-421)** sorts `workflow_phases` by its primary key, now `entity_uuid`.
   - **Step 4's "Before" query (plan:444)** becomes `SELECT e.uuid FROM entities e LEFT JOIN workflow_phases wp ON wp.entity_uuid = e.uuid WHERE wp.entity_uuid IS NULL AND e.workspace_uuid = ? AND e.kind <> 'project' AND e.is_deleted = 0` (28 on today's data). That is the backfill's own rule: it lists the workspace's entities, which leaves out soft-deleted ones (`list_entities`, database.py:8282), and skips projects (backfill.py:254), where the plan names three kinds. On today's data they select the same entities, since the live file holds only backlog, brainstorm, feature and project entities, and none is soft-deleted.
   - **Step 4's "Expected" (plan:446):** exactly those entities gain rows, each keyed by its own `entity_uuid`.
   - **Steps 1–3 (amended 2026-09-26) are unchanged.** Step 1's registration clause (plan:427) covers a brainstorm whose type_id only another workspace holds, which registers once RK2 removes 1C's skip.
6. **F2 (plan:457):** it runs after all four phases land, and Phase R has landed or the user has deferred it (recorded).
7. **F3 (plan:464):** when Phase R's branch is ready to land, it asks one question (Q5): land Phase R, migrate the live registry and publish, in one sitting with pd disabled in every session. The order is migrate, verify, land, publish (13.3). It asks at the same time about the five namesakes and the operator tool's fate (Q6, Q7).
8. **Done when (plan:474-484):** after #1, under a recorded deferral of Phase R's sitting, the type_id-only updates, W3.1–W3.3 and problem 1's read-scoping stay in this design's Deferred table, each marked to reopen when the sitting runs (section 14). #2 (plan:480) exempts tests that live only on `followups-phase-r` under a recorded deferral.

*Apply in the sitting's commit, which lands Phase R* (they state facts true only once it has landed):

9. **Problem 3 (plan:22-23):** the text after its title, "Every insert stores the resolved entity's `workspace_uuid` and `uuid`", becomes "every insert is keyed by the resolved entity's uuid; the row's workspace and type_id are the entity's, read by join". Its checks: W2.1's "Explicit workspace" test as restated (the W2 tests row above), `test_upsert_writes_own_row_leaves_namesake_unchanged`, `test_rekey_schema.py::test_insert_for_unknown_entity_is_refused` (`wp_reject_unknown_entity`; prototype `guard_insert_unknown_entity`), and F1 step 4 as restated. Its line "Deferred by design (D3): the type_id-only updates" (plan:23) goes: Phase R keys updates by entity uuid.
10. **The fingerprint baseline (plan:452, and Done-when #4, plan:482):** from the sitting on, F1's "the live file's fingerprint matches kickoff's" and #4 compare with the fingerprint the sitting records after the approved migration (13.3 step 6; playbook S9), which replaces kickoff's.

- **Outside Phase R's documents:** plan:370 (4C's files) still says "migration 11 or its concurrency test". The amended 4C brief makes it the migration runner (`_migrate` and `_migrate_v2`), so the orchestrator aligns that line when the plan is next edited.

## 13. Operations

### 13.1 The hazard: any open migrates

- **The mechanism:** `EntityDatabase(path)` runs the pending chain when it opens a file (`_migrate`, database.py:11078; `_migrate_v2`, :11191). Any process that opens the live file with code that holds RK2 would migrate it, with none of this section's backup or checks; the tripwire below makes that open refuse instead.
- **What could do it:**
  - a repo script run from the main checkout with the real HOME: `scripts/migrate_db.py`, `migrate.sh`, `plugins/pd/scripts/*` (for example `compare_backlog_projection.py`, which opens the default path, :120-128) or `python -m entity_registry.rebuild_tool`;
  - the UI server, started from the checkout;
  - a published build's session hooks;
  - a pd-enabled Claude Code session started in a Phase R clone: `sync-cache.sh`, a SessionStart hook (hooks.json), rsyncs that clone's `plugins/pd` over the cache (sync-cache.sh:12, :32), which publishes Phase R's code.
- **The rule, enforced by landing:** RK2 reaches develop only when Phase R lands whole (plan:67-70), and Phase R lands only in the RK6 sitting, after the user's yes (section 12's plan changes). So no deliberate publish holds RK2 code before the sitting, and the user's repo scripts, UI server and published hooks stay on version-7 code. A pd-enabled session started in a Phase R clone would publish it (above), so the common brief forbids that, and whether pd stays disabled until the sitting is the user's Q1 (section 9).
  - **Agents never open the live file:** from R4's start, every command an agent runs (tests, probes, scripts, servers) runs with `HOME=$(mktemp -d)` and `ENTITY_DB_PATH` unset, not only the gates (plan:380-381; the safety rules, plan:104-113). Each task's QA records the live file's `schema_version` (read with `immutable=1`) and its fingerprint (`stat -f '%m %z'`, `1790286038 4083712` at R3) before and after. A version other than 7, or a fingerprint change the task cannot explain, stops every task and goes to the user.
  - **The tripwire backs the rule:** migration 26/8 refuses the account's live registry. `_v2_migration_8_rekey_workflow_phases` (one function, both chains) raises `MigrationError` naming `scripts/rekey_live_registry.py` when it has rows to move (old-shape `workflow_phases` or `phase_events` rows) and the connection's main file (`PRAGMA database_list`) is the live registry: `os.path.samefile` with `$HOME/.claude/pd/entities/entities.db`, or with the same path under the account's passwd home. Only `PD_REKEY_APPLY=1` in the environment lifts it, and only the operator tool's `apply` sets it.
    - **Where it is inert:** fresh files, copies and re-keyed files. So F1's migrated copy of S and the rehearsal's copies still migrate on open.
    - **On any other machine** with a pre-rekey registry, pd refuses to start until the tool runs there.
    - **Test:** `test_rekey_migration.py::test_live_path_refuses_without_the_operator_flag[refuses|flag-set-migrates|copy-migrates|fresh-file-migrates]`, with a temp HOME; the refusal case also asserts the file stays byte-identical.
  - **The sitting itself:** preconditions 4 to 6 (13.3) close every pd process and check that the live file is still at version 7.
  - **How a breach would show:** the live file's `schema_version` reads 8 before the apply, and its `migration_audit_log` holds this migration's `success` row, dated before the sitting (precondition 6).
- **`pd_state_diff.py` is safe:** it opens its file read-only and fails soft (SCR-1, HOOK-4), so it can't migrate the file. On an old-shape file, new code's SQL fails and the hook stays silent.

### 13.2 What C23 means, while pd is disabled and after

- **The guard:** C23 refuses writes to a file whose version is higher than the build's maximum. It installs a SQLite authorizer that denies every mutating action (database.py:11113; `_refuse_if_file_is_from_the_future`, :11145-11179).
- **While pd is disabled** (today): no pd process runs, so the version bump strands nothing.
- **If pd is re-enabled before the new build is published:** every session's servers are the old build (maximum 7) on a version-8 file.
  - **Writes** are denied (prototype `c23_write`: "denied: not authorized"; `c23_future_file`: refused 8 against the build's maximum of 7).
  - **Reads** by type_id fail loudly (`c23_old_read_by_type_id`: "no such column: type_id").
  - **The effect:** nothing is written wrongly, but pd doesn't work until the publish. So the publish follows the migration in the same sitting.
- **After re-enabling, with the new build published:** 8 is the build's maximum, and C23 stays silent.
  - **A leftover old process,** from a session started before the publish, fails loudly on every workflow call. The prototype `old_process_open_during_bump` shows:
    - `update_workflow_phase` and `get_workflow_phase` fail with "no such column: type_id";
    - `append_phase_event` is refused by `pe_reject_live_event_without_entity`;
    - `phase_events` stays at 1469 rows.
  - **Restarting that session** fixes it only while the cache holds the new build. A pd-enabled session started on a pre-Phase-R branch in the main checkout republishes that branch's older plugin, since the cache's own `sync-cache.sh` runs at SessionStart and rsyncs the checkout's `plugins/pd`; a restart then starts the old build again. The cure: check out develop in the main checkout, run `plugins/pd/hooks/sync-cache.sh`, and restart the sessions.
- **The publish guard** (the playbook's R4-E ships it with Phase R): `sync-cache.sh` reads the source's `V2_SCHEMA_VERSION` (schema_v2.py) and the live file's `schema_version` read-only (`immutable=1`, or `mode=ro` when a `-wal` exists).
  - **If the source's value is lower,** it skips the rsync, says why in the hook's `additionalContext` JSON, and exits 0, since a hook never blocks a session.
  - **It fails open** when the registry is absent or unreadable.
  - **Test:** `test_sync_cache_refuses_an_older_schema_build` (a temp HOME with a v8 registry and a source at v7: the cache is unchanged). Task 3A also edits `sync-cache.sh`, in separate hunks.

### 13.3 The live migration (R2 writes it as the operator manual)

- **The playbook's Part 3 governs the sitting,** with the operator tool `scripts/rekey_live_registry.py`. It runs the steps below in the order migrate, verify, land, publish: it applies from a scratch clone at the exact commit develop will fast-forward to, verifies, and only then fast-forwards develop and publishes, so a failed verification needs a restore alone (playbook §0.2 item 6). The plan's F3 states that order (section 12, item 7).

**Preconditions:**
1. Phase R's branch (RK1–RK5), rebased onto develop, passes its integration QA: G1–G5 and F1 (adjusted, section 12).
2. R3's rehearsal passed (13.5).
3. The user said yes to Q5, the one F3 question: migrate, verify, land and publish.
4. No process holds the file: `lsof /Users/terry/.claude/pd/entities/entities.db` prints nothing, and no `-wal` exists.
   - **The operator** is the orchestrator, in a Claude Code session started with pd disabled at user level, as it has been since 2026-09-24.
   - **If the user re-enabled pd** after Phase 1's publish (F3), or during R4 (Q1's second option), the sitting starts with the user disabling it and restarting every Claude Code session, the operator's included, since pd's MCP servers hold the file open.
5. The fingerprint (`stat -f '%m %z'` and sha256) is compared with the one R3 rehearsed on.
   - **What changes it:** any writer: a pd session (its entity server's backfill, workflow tools and session hooks), a repo script run with the real HOME, or a WAL checkpoint. Reads with `immutable=1` or `mode=ro` don't.
   - **A change since R3** is expected once the user has used pd, so it doesn't stop the procedure: the phase report records both fingerprints and the cause, and step 2 re-derives every expected figure.
   - **A change during the sitting,** after step 1, stops it and goes to the user (step 3), as F1 stops on a changed fingerprint (plan:455).
6. The live file's `schema_version` is 7, read with `immutable=1`. An 8 means something migrated it outside this procedure: stop and ask the user.

**Steps:**
1. **Back up** with the prescribed `s.backup(d)` command, to `~/.claude/pd/entities/entities.db.pre-rekey-<YYYYMMDD>` (beside the earlier `pre-*` backups).
   - **Check the backup:** `PRAGMA integrity_check` is `ok` on it.
   - **Compare fingerprints:** its per-table fingerprints (F1's method: a sha256 over each table's rows, sorted by primary key) equal the live file's, read with `immutable=1`.
2. **Rehearse on a copy made the same minute,** with the code about to land, which R3 did not have (13.5):
   - open the copy with that code, and run section 5's queries and 13.5's steps 3 and 7;
   - every value must equal section 5's figure, or, if precondition 5 found a change, the figure the expected-figure queries (5.2) give on the backup; the phase report records both;
   - a mismatch stops the procedure.
3. **Apply,** from a scratch clone at the commit develop will fast-forward to:
   - check that the live fingerprint still equals step 1's; a change stops the procedure and goes to the user;
   - apply with the operator tool, which sets `PD_REKEY_APPLY=1` for its one open, since a bare `EntityDatabase` open of the live path refuses (13.1):
   ```
   scripts/rekey_live_registry.py apply --db /Users/terry/.claude/pd/entities/entities.db --backup <step 1's backup> --confirm-live
   ```
   The apply fails when a `-wal` remains after it closes (13.4).
4. **Verify the live file:**
   - section 5's post queries, with Q-rows-kept compared against the backup's pre query;
   - `PRAGMA integrity_check`;
   - `schema_version` is 8;
   - the audit row.

   Open the file read-only: with `immutable=1` when no `-wal` exists, otherwise with `mode=ro`.
5. **Land:** fast-forward develop to Phase R's branch (the plan's landing rule), and record the commit develop pointed at just before: the rollback's build (13.4).
6. **Record** the new fingerprint (`stat` and sha256) in the phase report, and make the read-only post-apply copy `entities.db.post-rekey-<YYYYMMDD>` that a later rollback diffs against (13.4).
7. **Publish** under the same yes: `sync-cache.sh` from the main checkout. The user then re-enables pd, or restarts sessions.

### 13.4 Rollback

- **When:** in the sitting: a verification query fails, or the new build misbehaves before any session has written the migrated file.
  - **After sessions have written it,** the recovery is to roll forward: fix the code and publish, keeping the file.
  - **A restore then** would lose those writes, so it needs the user's explicit choice, with the changed rows listed for re-entry (the last bullet).
- **How:**
  1. Stop every pd process, until `lsof` prints nothing.
  2. Copy the backup onto the live path with the same backup-API one-liner, reversed, with the source opened `immutable=1`.
  3. **Never delete a `-wal` or `-shm` by hand.** The backup API writes through a SQLite connection, which reads any `-wal` the migrated file left and then overwrites every page, so the restored content wins. After that connection closes, `ls` should show no `-wal`. If one remains, run the operator tool's `checkpoint --db <live> --confirm-live` before any check: one plain `sqlite3` connection, `PRAGMA wal_checkpoint(TRUNCATE)`, close. It reports fingerprints, sha256 and version before and after, never opens `EntityDatabase`, and never deletes a file.
     - **An apply killed inside its transaction** leaves the content unchanged, but a `-wal` and `-shm` that make every retry refuse. With `lsof` listing nothing, `checkpoint` clears them; then the per-table fingerprints decide. Equal to the backup's at version 7 means there is nothing to restore, and a retry starts again from the backup (playbook 3.4).
- **Verify:** `schema_version` is 7, the per-table fingerprints equal the backup's, and `integrity_check` is `ok`. The prototype did this on a copy: `rollback_sha256_matches_backup` is true, and `rollback_version` is "7".
- **The build must match the file.** If the new build was published, republish the last build from before Phase R: the develop commit 13.3 step 5 recorded. Otherwise the next session's Phase R build meets the restored version-7 file: the tripwire refuses to migrate it (13.1), so pd stops starting until the old build is back.
  - **From where:** `plugins/pd/hooks/sync-cache.sh` publishes the checkout it runs in (its source is `detect_project_root`'s `plugins/pd`, sync-cache.sh:11-13). So it runs from a scratch clone checked out at that commit, while the main checkout stays on develop.
  - **The yes:** the restore and the republish are one gated live write, on the user's yes.
- **Writes made between the apply and the rollback are lost.** Before restoring, fingerprint the migrated file and list the rows changed since the sitting in the phase report: the operator tool's `diff --db <live> --ref <post-apply copy>` (13.3 step 6) reports, per table, the rows only in one file and only in the other, as JSON, for re-entry. It is read-only, and it names any table whose columns differ.

### 13.5 What the R3 rehearsal must show

- **Which code:** R3's build, the playbook's changes on a scratch export of develop after Phase 1 (plan:310), since no Phase R code has landed when R3 runs. RK6 re-runs steps 2, 3 and 7 with the code about to land (13.3 step 2).
- **When each figure is taken:** the figures of step 2 are the migration's, measured before any server starts.

1. **The copy:** a fresh copy made with the prescribed command, with the live fingerprint unchanged before and after.
2. **The figures:** R3's build (not this prototype) migrates the copy, and section 5's queries give section 5's values:
   - `workflow_phases`: 529 of 529 preserved, 0 re-attached, 0 dropped, 0 stale, (366, 163) by archive flag, and the 5 shared rows;
   - `phase_events`: 1444 attributed, {0: 12, 2: 13} unattributed, 0 misattributed, and 1469 rows, max id and sequence;
   - one `success` audit row.
3. **One target:** the migrated copy, a fresh v1 file and a staging v2 file, all built by the same code, have identical `sqlite_master` text for both tables. The copy's views equal the staging file's.
4. **Resumability,** on copies:
   - killed inside the transaction;
   - crashed before the version stamp;
   - reopened, which is a no-op.
5. **An old build on the migrated copy** (the published pre-Phase-R cache, or a `4a6373f0` export): writes are denied, type_id reads fail loudly, and no row changes.
6. **Rollback on the copy:** restore, then check that sha256 and fingerprints equal the backup's, that the version is 7, and that the old build works on it again.
7. **The build serves the migrated copy.** Its two MCP servers and the UI start against it, with a temp HOME and `ENTITY_DB_PATH` set to the copy, twice: pinned to pedantic-drip, then to terry_agent (`ENTITY_WORKSPACE_UUID`, as F1 pins).
   - **The backfill runs first:** each start's entity server seeds rows for its workspace's row-less entities (W2.6), and reports how many it created. On today's data: 28 in pedantic-drip (25 backlog items, and the archived features 035, 112 and 113), and 6 in terry_agent (the five namesakes and feature 035, all archived).
   - **The board** then shows the migration's figures plus those rows: 366 + 25 = 391 cards in the `'*'` view, and 529 + 34 = 563 with archived ones, on today's data. On a changed file, the counts the backfill reports replace these.
   - **Reads:** `get_phase` for each of the five shared type_ids answers from the pinned workspace's own entity: pedantic-drip's rows when pinned there (for example `feature:002-assessed-mode-pipeline-fix` at `finish`), and terry_agent's newly seeded rows when pinned there.
   - **A write:** pinned to terry_agent, `transition_entity_phase` moves `brainstorm:20260318-025248-three-claws-v2-protocol` from `draft` to `reviewing` (router.py:203 allows it), and pedantic-drip's namesake row keeps its fingerprint. `transition_phase` on the archived namesake features is not part of the check: its gates read feature directories that the scratch setup doesn't carry.
   - **The Python the hooks launch,** each against the copy, pinned the same way: the session-start orchestrator (HOOK-1, as `session-start.sh` runs it), the doctor with `--fix` (HOOK-2) and `pd_state_diff.py` (HOOK-4). Each exits 0 with no traceback. HOOK-5 is the UI above; HOOK-3 reads no registry.
8. **F1** runs later, on Phase R's branch at R4's integration, with section 12's adjustments (13.3, precondition 1). R3 checks that the adjusted F1 queries run on the migrated copy.

## 14. Scope

**In, with reasons:**
- **`database.py`:**
  - the migration (section 4);
  - the row and event methods, resolvers and entity writers (section 6);
  - `PHASE_EVENTS_COLS` (schema-49), which gains `entity_uuid`;
  - the corrected v2 migration 3 docstring (4.3).
- **`schema_v2.py`:** `V2_SCHEMA_VERSION = 8` (schema-74).
- **The engines, both MCP servers, `server_helpers`, `frontmatter_*`, `dependencies`, `backfill` and the orchestrator:** the call-site edits (sections 6 and 8). `run_backfill`'s comparison, `check_workflow_drift`'s map and `list_by_status`'s map move to `entity_uuid` (guard rule 3). `query_phase_analytics` and `_compute_durations` (MCPW-43, fill-2) scope by the entity's workspace and pair events by `entity_uuid`.
- **The UI:** W3.1–W3.3 restated (section 7).
- **`rebuild_tool.py`** (schema-76 to -80): the staging build runs the new chain, so the copy lists and `_preimport_vocab_diff` follow the new shape, and an old-shape source is refused, with a message that names the operator tool and never tells the reader to open the source (open question 12).
  - **Its re-mint** gives every entity a new uuid (FR132-2; rebuild_tool.py:268-271). So both tables' `entity_uuid` values go through its old-to-new uuid map, where rows are matched by `(workspace, type_id)` today (`_import_workflow_phases`, rebuild_tool.py:786-850; the event copy, :1015-1072). An unattributed event keeps its NULL.
  - **Its verification** gains `PRAGMA foreign_key_check(phase_events)` (2.4).
- **The doctor:**
  - **re-keyed:** the `workflow_phases` part of `check_referential_integrity` (engines-91) reports the rows `PRAGMA foreign_key_check(workflow_phases)` and `PRAGMA foreign_key_check(phase_events)` return, with no fix. Only a raw-SQL hard delete with foreign keys off can leave one (4.2), and deleting history is the user's call;
  - **deleted:** `_fix_remove_orphan_workflow` (engines-92), with its dispatch entry;
  - **writes by uuid:** `_fix_self_referential_parent` (engines-93);
  - **one entry fewer:** `check_status_write_path`'s permitted list drops `delete_workflow_phase` (engines-94).
- **`plugins/pd/scripts`:**
  - `pd_state_diff.py` (SCR-1, SCR-2) joins and replays by `entity_uuid`;
  - `cleanup_backlog.py` (SCR-3) passes its workspace.
- **Deleted:**
  - `delete_workflow_phase`;
  - server_helpers' `parent_type_id` branch;
  - `scripts/c22_recreate_live_remainder.py` and `scripts/test_c22_recreate_live_remainder.py`: a one-off that has already run, whose SQL can't run on the target shape (SCR-9, SCR-10, tests-65);
  - `scripts/fix_kanban_columns.py` and `scripts/test_fix_kanban_columns.py`: a "One-time fix" (its docstring) named in rev 2.1's deferred list (SCR-5, SCR-6, tests-66);
  - the orphan-tolerance code and its test cases (open question 14); the doctor's report stays, re-keyed (above).
- **After the sitting, if the user agrees (Q7):** the operator tool `scripts/rekey_live_registry.py` and its tests, by the same one-off rule (recommended). F2's commit deletes them; a later restore follows the playbook's 3.5 written steps with plain `sqlite3`. If the user keeps the tool, this section records the reason, and the tool stays behind `--confirm-live` and its live-path guard.
- **The docs that restate the key.** RK2's implementer runs this grep:

  ```
  git grep -n -E 'workflow_phases|phase_events|append_phase_event|query_phase_events|get_workflow_phase|upsert_workflow_phase|create_workflow_phase|update_workflow_phase|delete_workflow_phase' -- '*.md' ':!docs/plans' ':!docs/features' ':!docs/brainstorms' ':!docs/projects' ':!docs/rca' ':!docs/knowledge-bank' ':!CHANGELOG.md' ':!agent_sandbox'
  ```

  - **What it excludes:** records, which stay as written.
  - **At `4a6373f0`:** 39 lines in 8 files (`calvin/docs_key_grep.out`), among them `README_FOR_DEV.md:451` (inventory 10.6, O3).
  - **Who checks it is complete:** the task report gives each line a disposition (edited, or states no key), and the task's reviewer re-runs the grep on the branch. The playbook gives this sweep its own task, R4-H.
- **Code comments that restate the old key.** R4-H's second grep, over code, prints nothing outside records and tests that name a removed behaviour:

  ```
  git grep -n -E 'keyed by type_id|type_id alone|until Phase R|\(Phase R\)|Known gap' -- '*.py' '*.sh'
  ```

  - **Known hits at `c1bbfae0`:** `check_workflow_drift`'s docstring (reconciliation.py:555-563, "reads the row by type_id alone"), which RK1 restates when it passes the workspace; `reconcile_status`'s (workflow_state_server.py:2546-2553, "Workflow rows are keyed by type_id") and 1C's skip paragraph (entity_status.py:21), which RK2 restates or deletes. The grep also prints 1C's skip warning (entity_status.py:165) and its test (test_brainstorm_registration_scoped.py:20, :274), 1B's test_reconcile_status_scoped.py:8 ("`workflow_phases` is keyed by type_id"), `test_build_workflow_lookup_correct_keys`' docstring (ui/tests/test_entities.py:28), and `upsert_entity`'s docstring (database.py:7857), which makes no row-key claim.

**Out, with reasons:**
- **`scripts/migrate_db.py merge-entities` (SCR-7) and `migrate.sh import`'s entity merge:** broken since migration 11; the user decides (Q4).
  - **If deleted, as recommended:** R4-E deletes `cmd_merge_entities` (migrate_db.py:199) and its subparser (:618-627), `TestMergeEntities` (scripts/test_migrate_db.py:325) and `test_migrate_deepened.py`'s merge tests, and `migrate.sh import`'s merge step becomes a loud refusal counted in `import_failures`.
  - **If kept:** it stays out, with its Deferred row.
  - `cmd_manifest` and `cmd_migrate` (SCR-8) only count rows, so they are unaffected.
- **Test files out with it:**
  - `scripts/test_migrate_bash.sh` (TST-3), which hand-rolls its own DDL;
  - tests-67 to -69, apart from `TestMigration6`'s three row assertions (`test_migration_no_orphaned_workflow_phases`, `test_migration_no_null_uuids_in_workflow_phases` and `test_migration_workflow_phases_uuid_backfill`; scripts/test_migrate_db.py:941). Those already reach the head chain through `cmd_migrate`'s `EntityDatabase` (migrate_db.py:391, :488), so RK2 restates them for the new key, whether or not 4B lands. G5's base keeps TestMigration6's 7 existing failures.
- **`scripts/dev/cutover-prepass.sql` (SCR-11):** a one-off from the v2 cutover that has already run. It updates `phase_events.phase` by value, not by key.
- **`scripts/seed-census-db.py` (SCR-12):** it writes only a synthetic v2 events file, never either table.
- **`plugins/pd/scripts/parse_backlog_md.py` (SCR-4):** it touches neither table. Its match of backlog entities by `entity_id` in every workspace is a separate cross-workspace write, recorded as Deferred below.
- **Hooks (HOOK-1 to -5):** they reach the tables only through the Python they launch. R3's step 7 runs that Python (13.5).
- **Command and skill markdown (MD-1 to -25):** tool parameters are unchanged (6.5).
- **Pedantic-drip's five namesakes** (5.3): a data decision for the user (Q6: no change, archive them, or merge them into terry_agent's copies).
- **Refusing cross-workspace duplicate type_ids at registration** (rev 2.1's Deferred, D3 (B)): still deferred. The re-key makes duplicates harmless for workflow rows and events. What they still cost: two items with one type_id in all-workspaces views, a type_id URL that needs a uuid cookie selecting its workspace (section 7), and SCR-4's cross-workspace write (Deferred below).

**New Deferred rows:**

| Item | Reopen when |
|---|---|
| `update_workflow_phase` and `upsert_workflow_phase` emit no v2 event (inventory O1) | `workflow_phases` is retired in favour of a view |
| The `ready` value the `kanban_column` CHECK lacks (schema-73) | the next vocabulary pass |
| The 25 unattributed `phase_events` rows (the undecided and no-holder classes) | a stored fact decides an undecided row's holder; an explicit repair may then set them once |
| `parse_backlog_md.py` updates every workspace's backlog entity with a matching `entity_id` (SCR-4) | the script next runs against a registry with shared backlog ids |
| `migrate_db.py merge-entities` for per-entity keys, if the user keeps it (Q4) | a cross-machine import is next needed |
| Pedantic-drip's five namesakes, whose artifacts exist only in `/Users/terry_agent/docs` (5.3) | the user rules on archiving or merging them (Q6) |

**Under a recorded deferral of Phase R's sitting** (Q1's third option, or Q5's Defer), three more rows join this table, each marked to reopen when the sitting runs: the type_id-only updates (D3), W3.1–W3.3, and problem 1's read-scoping. 1C's skip stays with them (section 1.3).

## 15. Work breakdown

The tasks follow expand, migrate, contract, an order chosen so that each merge can keep G1–G5 green. Nothing has shown that yet: this design ran no test suite (question 24). R3's code verification checks it on the playbook's build, and each task's QA enforces it.
- **Order:** RK1 → RK2 → RK3, with RK4's three codemod slices beside RK3 → RK4's strict flip → RK5 → RK6. The playbook's R4-C0 runs beside RK1, and its operator tool (R4-E) beside RK3.
  - **Why RK4's flip follows RK3:** `plugins/pd/ui` holds 3 production and 24 test calls the strict rule touches (`calvin/churn_ui_only.out`), and RK4's gates run `ui/tests`. RK3 scopes them first. The codemod slices are additive under the fallback, so they need not wait for it.
- **When R4 starts:** once 2A and 2C have landed on develop (Phase 1 has, at `c1bbfae0`) and the user has answered Q1 "hold the sitting this round" (section 9). The prerequisites table below lists every gate.
- **Each task:** runs the plan's review protocol, gates and landing rules. Its rows are its checklist (inventory ids; lines re-anchored by symbol on the task's own branch, plan:72). Its red-first tests are the section 10 tests it owns.

**The playbook's tasks.** The playbook slices the work units into tasks. R3 split RK4 into four and added R4-C0; the evidence is the blast census at `ddc299a0` (6.4) and R3's disposition rows, named in parentheses.

| Task | Design unit | Scope R3 added | Depends on (inside Phase R) | Outside prerequisites | Can run beside | Gate expectation |
|---|---|---|---|---|---|---|
| **R4-A** | RK1, the library and engine half | the entry-point table (PM-CODE-W4); `frontmatter_sync_cli.py`, the read-only CLI resolver, `cleanup_backlog`'s lookup order and `backfill_headers`' scope (PM-CODE-W9); the test_c11 rewrite and deletions (BLAST-B3); `_process_export_lineage_markdown`'s workspace parameter (BLAST-W2); `check_workflow_drift`'s docstring (PM-CONS-W2); the corrected uuid test (PM-CODE-B1) and `set_deleted` by uuid (PM-CODE-W6) | none | Phase 1 (landed, `c1bbfae0`); 2A and 2C landed; Q1 answered "hold the sitting this round" | R4-C0 | **G1** grows by the three new files and shrinks by the 4 `delete_workflow_phase` tests, the `parent_type_id`-branch tests and the two test_c11 deletions (the report lists each). **G2** grows by `test_cleanup_backlog_workspace.py`. **G3–G5** unchanged |
| **R4-C0** (new) | RK2's test preparation, moved before it | shape-aware test helpers in `test_helpers.py`, keyed by the entity's uuid: write a workflow row, read it, insert a phase event. On the old shape a helper looks up the entity's `(workspace_uuid, type_id)` and writes those columns; on the new, it writes `entity_uuid`. `PRAGMA table_info` detects the shape. Every raw-SQL statement on `workflow_phases` and `phase_events` in test files moves behind them. Out: tests that stop the chain before 26/8 or pin a historical schema; `scripts/test_migrate_db.py` (RK2 owns `TestMigration6`); the files RK2 deletes; tests whose subject is an orphan row; the tests pinning the row key that RK2 restates (1A's four files, 1C's skip tests) (PM-CODE-W11) | none | as R4-A | R4-A, R4-B | **G1–G5**: failures equal the base's. No assertion changes; the report lists every converted statement |
| **R4-B** | RK1, the MCP half | `server_helpers.py` (BLAST-W2); MCPE-10's `resolve_ref` (PM-CONS-W2); the label-only calls and the NULL-legacy fixture (PM-CODE-W8); the handler entry-point table (PM-CODE-W4) | R4-A | none beyond R4-A's | R4-C0 | as before: G1 grows by its new test files; G2–G5 unchanged |
| **R4-C** | RK2 | as before, minus the per-file raw SQL (now R4-C0's helpers). Plus: 1C's skip removed (BLAST-B2); the four mismatch tests (BLAST-W1); `TestMigration6`'s three assertions (BUILD-W2); the migration_14 fixture (BUILD-S6); the live-path tripwire (PM-CONS-W5); the v2-chain race test (BLAST-B1); the label predicate (PM-LIVE-W8); the uuid cases for `update_workflow_phase` and the two `phase_events` pairs (PM-CODE-B1); raw-SQL seeding (BUILD-W3); the stale-view fixture (BUILD-S4); the SQL-free fault seam (PM-CODE-W3); non-vacuous migration tests (PM-CODE-W5); the rebuild message (PM-LIVE-W5); `query_phase_events_bulk`'s uuid check (BLAST-S4) | R4-B, R4-C0 | 4C landed; otherwise R4-C carries 4C's contract (BLAST-B1) | none | **G1**: new files, and the listed rewrites and deletions. The 16 `test_c19_c20b` tests are green at its head. 4C's race tests are green with migration 26 registered, with no re-run allowance. **G5** shrinks by the deleted scripts' tests (measured: 32 C22 tests at `ddc299a0`, plus `test_fix_kanban_columns.py`'s); `TestMigration6`'s 3 are rewritten; the base keeps 7 failures. **G2** unchanged unless a scripts test reads a changed column. **G3–G4** unchanged |
| **R4-D** | RK3 | the three cookie states (PM-CODE-W7) | R4-C | none | R4-E, R4-F1, R4-F2, R4-F3 | as before |
| **R4-E** | none: the playbook's operator tool | `checkpoint` (PM-LIVE-W10), `diff` (PM-LIVE-W6), the swap guards (REH-W1), both live-path forms (PM-LIVE-W1), P4's settings files (PM-LIVE-S2), fingerprint versions and the table set (REH-S1, PM-LIVE-W2), the pinned contract (BUILD-S8), `expect` without paths (REH-W4), try/finally (REH-S9), `restore`'s check names (REH-S3); the `sync-cache.sh` guard (PM-LIVE-W4); merge-entities' deletion if Q4 = delete (PM-CONS-W7) | R4-C | 3A's `sync-cache.sh` edit in a separate hunk | R4-D, R4-F1, R4-F2, R4-F3 | **G5** grows by `scripts/test_rekey_live_registry.py`. If merge-entities is deleted, G5 shrinks by `TestMergeEntities` and `test_migrate_deepened.py`'s merge tests (measured). **G4** runs, with the new sync-cache test. **G1–G3** unchanged |
| **R4-F1** (new) | RK4, codemod slice 1 | the codemod, extended by the entry-point table, on `plugins/pd/hooks/lib/entity_registry` tests (31 files) and G2's three scripts tests (`test_cleanup_backlog.py`, `test_parse_backlog_md.py`, `test_c5b_parse_backlog_workspace.py`). Rows: tests-12, -17, -28 to -32, -70, -71, and tests-72's entity_registry and scripts files. Also feature 129's two calls (PM-CODE-B2), and `match=` on its share of the 16 `pytest.raises` blocks (PM-CODE-W1) | R4-C | Q2 = strict | R4-D, R4-E, R4-F2, R4-F3 | **G1–G5** unchanged (additive under the fallback). **QA:** the record-only census shows 0 would-be refusals from the slice's files, and the leftover list is closed |
| **R4-F2** (new) | RK4, codemod slice 2 | the codemod on `plugins/pd/hooks/lib/workflow_engine` (15 files) and `reconciliation_orchestrator` (5 files) tests. Rows: tests-33 to -37, -41 to -45, -47, -49, -50. 1B's `test_session_start_reads_no_files.py` and `test_get_state_without_hydration.py`, and 1C's test file (its non-skip tests), with assertions unchanged (PM-CONS-W8) | R4-C | Q2 = strict | R4-D, R4-E, R4-F1, R4-F3 | as R4-F1 |
| **R4-F3** (new) | RK4, codemod slice 3 | the codemod on `plugins/pd/mcp` tests (13 files; `test_workflow_state_server.py` has 418 sites). Rows: tests-51 to -57 and tests-72's mcp files; 1B's `test_reconcile_status_scoped.py` and `test_update_entity_archived.py` | R4-C | Q2 = strict; 4A landed (it deletes tests in `test_workflow_state_server.py`) | R4-D, R4-E, R4-F1, R4-F2 | as R4-F1 |
| **R4-F4** (new) | RK4, the strict flip | the playbook's R4-F4 changes (1.8.4). Plus: `WorkspaceRequiredError` with the parameter-naming message, re-raised everywhere, the swallowing callers converted, and `test_refusal_reaches_the_caller` (PM-CODE-W1, PM-CODE-S4); R4-F's red-first tests, and its existing-test deletions and rewrites; the list tools' change, if Q3's yes came after R4-B merged | R4-D, R4-F1, R4-F2, R4-F3 | Q2 = strict | none | **G1**: failures equal the base's, apart from the listed adds, deletions and rewrites. **G2–G5** unchanged. **QA:** the record-only census over all of G1 shows 0 refusals outside `test_naming_rule.py` and 0 swallowed; label-only stragglers are 0 |
| **R4-G** | RK5 | the guard's widened rules (PM-CODE-W2) and the event-label check (PM-CONS-S6) | R4-E, R4-F4 | Q4 answered | R4-H | as before |
| **R4-H** | the docs sweep, split from RK2 | the code-comment grep (PM-CONS-W2; section 14) | R4-F4 | none | R4-G | as before |
| **R4-I** | RK6 | Part 3's changes | R4-G, R4-H, integration (playbook 1.12) with its per-rebase checklist (PM-CONS-W4), R3's rehearsal | Q5's yes | none | Part 3 |

- **Sizing rule** (PM-CODE-W4): before a codemod slice's implementer starts, the orchestrator runs the codemod on the slice's base. If it leaves more than 150 hand edits, the slice is split by file.
- **Order** (the playbook's §1.1 draws it):
  - R4-A → R4-B;
  - R4-B and R4-C0 → R4-C;
  - R4-C → R4-D, R4-E, R4-F1, R4-F2, R4-F3, in parallel, within the plan's cap of 6 agents;
  - R4-D, R4-F1, R4-F2 and R4-F3 → R4-F4;
  - R4-E and R4-F4 → R4-G; R4-F4 → R4-H;
  - R4-G and R4-H → integration (playbook 1.12) → R4-I.

**Prerequisites:**

| Gate | Condition | Evidence | What happens if unmet |
|---|---|---|---|
| **R4's start** (R4-A, R4-C0) | Phase 1 landed (done, develop `c1bbfae0`); 2A and 2C landed; Q1 answered "hold the sitting this round" | plan:316 ("once Phase 1 and 2A"); 2C edits `_resolve_ref_param`, which R4-B's change 3 touches; R4's roughly 1,800 test-site edits pay off only at the sitting | R4 waits. If Q1 = "not this round", R4 does not start, and the deferral is recorded (section 12, item 8) |
| **R4-C** | R4-B and R4-C0 merged; 4C landed on develop | without 4C's serialized, monotonic runner, migration 26 bricks files (12 of 20 rounds, 4.4) | R4-C carries 4C's five-point contract (the 4C brief's amendment) and tells 4C's owner |
| **R4-F1, R4-F2** | R4-C merged; Q2 = strict | Q2's alternative replaces the codemod with a bound default workspace | they wait; under the alternative, the orchestrator re-plans R4-F before any slice starts |
| **R4-F3** | as R4-F1, and 4A landed | 4A deletes tests in `test_workflow_state_server.py` (plan:371), the file with 418 of R4-F3's sites | R4-F3 waits for 4A |
| **R4-F4** | R4-D, R4-F1, R4-F2 and R4-F3 merged | the flip turns every unscoped call into a refusal | none |
| **R4-G** | R4-E and R4-F4 merged; Q4 answered | the guard's declared entries depend on Q4 | R4-G waits for Q4 |
| **R4-I** | R4-G, R4-H, integration (with the per-rebase checklist), R3's rehearsal; Q5 = yes | Q5 (section 9); the plan's F3 (plan:464) | Phase R stays on its branch under the rebase rule |
| **Not prerequisites** | 4B: R4-C owns `TestMigration6`'s three assertions (section 14). 3A: its `sync-cache.sh` change is a separate hunk from R4-E's guard, and the sitting's publish check and the rollback's republish are re-checked at each rebase | | |

- **The per-rebase checklist** (playbook 1.12; PM-CONS-W4). While the sitting waits, each rebase of Phase R onto develop:
  1. re-runs the codemod and the record-only census on the test files that arrived since the last rebase (0 would-be refusals);
  2. re-runs 6.2's uuid greps, and a grep for `row['type_id']` and `.get('uuid')`, on the code that arrived;
  3. if 3A landed: re-checks the sitting's publish check and the rollback's republish against the landed `sync-cache.sh`, and keeps R4-E's guard hunk;
  4. if 4C landed: checks that the migration runner is serialized, that its race tests pass with 26 registered, and that Phase R's tests patch no `PID_DIR` or watchdog by hand;
  5. if 4A's W5.7 landed: re-checks the `backfill.py` and `engine.py` deletions against R4-A's and R4-F4's edits;
  6. records each item's result in the integration report.

**RK1: the workspace reaches every call (expand).** The strict rule is not on yet, so the global-unique fallback still answers a type_id that one workspace holds, and existing callers keep working. One behaviour changes on purpose: `set_archived` and `set_deleted` with no workspace on a shared type_id raise the existing "Ambiguous" `ValueError` (database.py:7041-7057), instead of writing every namesake (:8470-8475, :8505).
- **Library (additive):**
  - `get_entity`, `get_workflow_phase` and `feature_entity_id` gain `workspace_uuid`, as do the feature-directory helpers and the engines' read paths (6.3, section 8);
  - `set_archived` and `set_deleted` resolve, then write by uuid, which closes the namesake-wide UPDATE now; `set_deleted` gains the uuid path `set_archived` has had since 1B;
  - `delete_workflow_phase` is deleted.
- **Callers:** every production site of section 8, and the production calls of 6.4 outside `plugins/pd/ui` (RK3 owns those), pass the workspace they have. The exception is the `phase_events` readers: they can only be scoped once the column exists, so RK2 owns them.
  - `cleanup_backlog.py` passes its workspace.
  - server_helpers' `parent_type_id` branch is deleted.
  - RK1 writes the entry-point table (section 8).
  - The CLIs resolve read-only, never with a minting resolver, and `cleanup_backlog.py` resolves before its archive loop (section 8).
  - `_process_export_lineage_markdown` (server_helpers.py) gains a `workspace_uuid` parameter, and the `resolve_ref` call 1B added to `_process_update_entity` (entity_server.py:399, MCPE-10) passes the workspace.
  - The label-only calls (6.5) pass the workspace or a uuid.
  - `check_workflow_drift`'s docstring (reconciliation.py:555-563) is restated for the per-entity read, in the same change that passes it the workspace.
- **Files:**
  - `entity_registry/database.py`;
  - `workflow_engine/` `engine.py`, `entity_engine.py`, `feature_lifecycle.py`, `feature_paths.py`, `reconciliation.py`, `rollup.py`, `router.py`, `secretary_intelligence.py`, `task_promotion.py`;
  - `entity_registry/` `backfill.py`, `dependencies.py`, `frontmatter_inject.py`, `frontmatter_sync.py`, `frontmatter_sync_cli.py`, `server_helpers.py`;
  - the test files `test_c11_feature_entity_id.py` and `test_c11_feature_paths.py` (6.3's `feature_entity_id` row);
  - `reconciliation_orchestrator/` `entity_status.py`, `dependency_freshness.py`;
  - `mcp/` `workflow_state_server.py`, `entity_server.py`;
  - `plugins/pd/scripts/cleanup_backlog.py`.
- **Rows:**
  - schema-32, -34, -36, -38, -44 to -46, -50, -52, -54 to -58, -66, synth-1;
  - engines-1 to -6, -10 to -42, -46 to -82, -87, -89;
  - MCPW-1 to -21, -23, -25 to -29, -32 to -42, -44 (W1 deletes MCPW-31; MCPW-22, -24, -30 and -43 are in RK2);
  - MCPE-1 to -16, synth-2;
  - SCR-3.
- **Tests:** `test_naming_rule.py::test_type_id_resolves_only_in_callers_workspace[...]`; `test_set_archived_without_workspace_on_shared_type_id_raises` (red on RK1's base, which archives both namesakes); `set_deleted` by uuid soft-deletes only that entity (red on base, where it raises), and `set_archived` by uuid archives only that entity (keep-green since 1B); `test_apply_archival_archives_nothing_when_the_workspace_does_not_resolve` (red on base, whose loop archives first); and `test_uuid_resolves_its_entity_whatever_the_workspace[<pair>]` (15 pairs: red on base for five, keep-green for ten; 6.1). The existing suites stay green, apart from 6.3's three test_c11 rewrites and deletions.

**RK2: the schema flip (migrate).**
- **The migration:** `_v2_migration_8_rekey_workflow_phases` on both chains, `V2_SCHEMA_VERSION = 8`, and the view re-creation (section 4).
- **Every statement on the two tables:**
  - the row view;
  - `append_phase_event`, `query_phase_events` and `query_phase_events_bulk` (6.3), and the four readers that scope by them: `_check_artifact_completeness`, `get_mini_spec`, `_detect_phase_events_drift`, and `query_phase_analytics` with `_compute_durations`;
  - the deleted `update_entity` cascade;
  - `rebuild_tool`;
  - `pd_state_diff`;
  - the doctor (section 14).
- **Maps keyed by `entity_uuid`:** guard rule 3's three engine sites (`run_backfill`, `check_workflow_drift`, `WorkflowStateEngine.list_by_status`) move off `type_id`. They need the row view's `entity_uuid` first. The two UI sites are RK3's.
- **Deletions:** the C22 script, `fix_kanban_columns.py`, orphan tolerance and the doctor's orphan fix, each with its tests; the doctor's orphan check is re-keyed (section 14). And 1C's skip, with its tests rewritten (6.1).
- **Also in the migration:** the live-path tripwire (13.1) and the label-decided predicate (5.2).
- **Prerequisite:** 4C has landed on develop (4.4). If it has not when RK1's MCP half (R4-B) merges, RK2 carries 4C's five-point contract (the 4C brief's amendment) and its race tests, and the orchestrator tells 4C's owner.
- **First check:** before editing, RK2's implementer looks in the landed Phase 1 code for C8's orphan `db_only` branch in `reconciliation.py`, and records whether W1 left it (question 14).
- **Tests:**
  - the raw-SQL fixtures and pinned-schema tests (open question 21);
  - `test_helpers.make_pre_rekey_db` (open question 22);
  - `test_rekey_schema.py` and `test_rekey_migration.py` (section 10);
  - the criterion-2 and criterion-3 tests, `test_upsert_writes_own_row_leaves_namesake_unchanged` and `test_mini_spec_of_a_is_invisible_to_b` (section 10);
  - 4C's race tests with migration 26 registered, and `test_two_runners_on_a_pre_rekey_v2_file_migrate_once` (4.4), with no re-run allowance;
  - `test_live_path_refuses_without_the_operator_flag[...]` (13.1);
  - `TestMigration6`'s three row assertions, restated for the new key (section 14);
  - the four `workspace_uuid mismatch` tests, which now expect the not-found error (6.3);
  - `test_rekey_event_streams.py::test_bulk_read_refuses_type_ids` (6.3);
  - the uuid cases for `update_workflow_phase`, `append_phase_event` and `query_phase_events` (6.1).
- **Files:**
  - `entity_registry/` `database.py`, `schema_v2.py`, `views.py` (read only: the view text is the target), `rebuild_tool.py`;
  - `doctor/` `checks.py`, `fix_actions/__init__.py`, `fixer.py`, `check_status_write_path.py`;
  - `mcp/workflow_state_server.py` (the four `phase_events` readers);
  - `plugins/pd/scripts/pd_state_diff.py`;
  - the deleted scripts;
  - `reconciliation_orchestrator/entity_status.py` (1C's skip), with `test_brainstorm_registration_scoped.py`, `test_c5b_brainstorm_workspace.py`, `test_entity_status.py` and `test_orchestrator.py`;
  - `workflow_engine/test_engine.py` (the mismatch tests) and `scripts/test_migrate_db.py` (`TestMigration6`);
  - the test files of the rows below, whose raw SQL on the two tables R4-C0 has already moved behind shape-aware helpers (the table above).
- **Rows:**
  - schema-11 and -19, the final shapes the target replaces;
  - schema-20 to -23: the registries, `_migrate`/`_migrate_v2`, no down step, and the v2 migration 3 docstring;
  - schema-26 to -31, -33, -35, -37, -39 to -43 and -49: the statements;
  - schema-68: the audit rows;
  - schema-74;
  - schema-76 to -80;
  - engines-91 to -94;
  - MCPW-22, -24, -30, -43, fill-2: the `phase_events` readers;
  - SCR-1, -2, -5, -6, -9, -10;
  - tests-1, -2, -4 to -11, -13 to -16, -18 to -27, -38 to -40, -46, -48, -58 to -66, -73;
  - schema-102 to -106, the events tests, re-run and edited only if they break;
  - 1A's four new test files, which have no inventory row, since the inventory is at `77f06efb`: `test_workflow_phase_writers.py`, `test_backfill_scoped.py`, `test_create_feature_lanes.py` and `test_projection_names_directory.py`. They read `workflow_phases` or a row's `uuid` and `workspace_uuid` keys;
  - 1C's `test_brainstorm_registration_scoped.py`, which has no inventory row either (1C landed after the inventory's commit): its skip tests are rewritten (6.1).
- **Tests (red first):** each section 10 test of criteria 1, 2, 3, 5 and 6 that RK2 owns is red on RK1's head for a behavioural reason, except the three keep-green criterion-2 tests (section 10).

**RK3: the UI on the new key (W3.1–W3.3 restated).** It runs before RK4's strict flip, beside its codemod slices, and owns every edit under `plugins/pd/ui`, including the 3 production and 24 test calls there that the strict rule touches, which it scopes.
- **What changes:** templates link by uuid; the detail route, the Entities page lookup and mermaid are keyed by uuid; W3's restated tests.
- **Files:**
  - `ui/routes/entities.py`, `ui/routes/board.py`, `ui/routes/helpers.py`;
  - `ui/mermaid.py`;
  - `ui/templates/_card.html`, `_entities_content.html`, `entity_detail.html`;
  - `ui/tests/*`.
- **Rows:** UI-1 to -10.
- **Tests (red first):**
  - the card link answers 200 with the owner's entity;
  - each namesake shows its own status on the Entities page;
  - the detail page's lineage for a shared type_id is not empty;
  - the mermaid graph has an edge per parent;
  - a type_id URL answers the 404 page with no cookie and with the `'*'` cookie, and resolves in the workspace a uuid cookie selects (section 7).

**RK4: the strict contract (contract).** The playbook runs it as four tasks (the table above): three additive codemod slices, R4-F1 (entity_registry and G2's scripts tests), R4-F2 (workflow_engine and reconciliation_orchestrator) and R4-F3 (mcp), then R4-F4, the strict flip.
- **What changes:**
  - the refusal becomes `WorkspaceRequiredError`, re-raised everywhere, and the callers that swallow it today are converted, each with `test_refusal_reaches_the_caller[<site>]` (6.1, section 8);
  - `_resolve_identifier` drops the global-unique branch;
  - `resolve_ref`'s exact and prefix matches need a workspace;
  - `search_by_type_id_prefix` requires one.
- **The codemod:** it adds `workspace_uuid=<the workspace in scope>` to the test call sites 6.4 measures (about 1,800 at `ddc299a0`, outside `plugins/pd/ui`), through RK1's entry-point table too, and lists, for hand edits, the calls in a scope with two or more workspaces (6.4).
  - **Each slice's first check** records the per-function classification (one workspace, several, none) and its leftover list.
  - **Each slice** adds `match=`, naming the expected error, to the `pytest.raises` blocks in its tree that wrap a no-workspace naming call (16 in all, premortem `probes/raises_names.out`).
  - **Each slice's QA** runs the record-only census on the slice's tree: 0 would-be refusals from the slice's files. Its leftover list is closed: every hand edit listed, with its function and why. That replaces a sample of hand edits.
  - **The flip's QA** runs the census over all of G1: 0 refusals outside `test_naming_rule.py`, 0 swallowed, and 0 label-only stragglers.
- **Files:** `entity_registry/database.py`, and the test files of the rows below.
- **Rows:** schema-50, -54, -57 (the strict half); tests-12, -17, -28 to -37, -41 to -45, -47, -49 to -57, -70 to -72.
- **Tests (red first):** `test_naming_rule.py::test_type_id_without_workspace_raises[...]`, on every `ENTITY_NAMING_METHODS` entry; `test_naming_rule.py::test_refusal_reaches_the_caller[<site>]`, red on the flip's base, where each site swallows the refusal.

**RK5: the guard.**
- **What lands:** `doctor/test_entity_keyed_access.py` (section 11), with the declared inventory and its high-water mark, the widened rules with their self-tests, and rule 6, the event-label check.
- **When:** after RK4 and the operator tool (R4-E), so that the detected set equals the inventory, and once the user has answered Q4, on which the declared entries depend. When RK5 is cut, the orchestrator checks develop for task 4A.
  - **If 4A has landed,** `display._rename` is gone and isn't declared.
  - **If not,** it is declared. While Phase R waits, 4A cannot edit the guard, which exists only on `followups-phase-r`, so Phase R's rebase fix-up removes the entry once 4A has landed on develop. If 4A lands only after Phase R, 4A removes it (section 11).
- **Red first:** on RK2's head, it fails with the RK3 and RK4 sites listed.
- **Rows:** tests-3 (the model, unchanged); the guard's own row set is section 11's 34 sites.

**RK6: the live migration (operator; needs the user's yes).**
- **What it follows:** section 13.3, after R3's rehearsal (13.5).
- **The landing and the publish:** in the same sitting, under the same yes (Q5): migrate, verify, land (fast-forward develop), publish, as the playbook's Part 3 runs them (13.3).
- **Files:** none in the repo. The phase report records the fingerprints and query results.

**Rows no task edits.** Each was checked for the re-key:
- **Historical migrations,** kept as written and allowed by the guard: schema-1 to -10, -12 to -18, -24, -25, fill-1.
- **Already keyed by uuid, or holding no entity key:** schema-47, -48, -51, -53, -59 to -65, -67, -69 to -71.
- **Read by the migration as its target:** schema-72 (views.py's text).
- **Deferred:** schema-73.
- **Deleted by W1:** engines-7 to -9, -43 to -45, -84 to -86, -88, -90, MCPW-31.
- **Deleted by task 4A:** engines-83 (W5.1) and fill-3 (W5.2).
- **Out** (section 14): SCR-4, -8, -11, -12, TST-3, and tests-67 to -69 apart from `TestMigration6`'s three row assertions (RK2's). SCR-7 (merge-entities) is out only if the user keeps it (Q4); if it is deleted, as recommended, R4-E deletes it with `TestMergeEntities` (tests-67) and the merge tests of `test_migrate_deepened.py` (tests-69).
- **Reached only through the Python they launch** (R3 step 7): HOOK-1 to -5.
- **Tool parameters unchanged** (6.5): MD-1 to -25.

**Coverage:** `work/task_rows_check.py` assigns all 369 inventory rows to exactly one task or to this list (0 missing, 0 duplicated). The four test files 1A added after the inventory's commit have no rows; RK2 owns them (above). 1B's four test files (`test_session_start_reads_no_files.py`, `test_get_state_without_hydration.py`, `test_reconcile_status_scoped.py`, `test_update_entity_archived.py`) and 1C's `test_brainstorm_registration_scoped.py` have none either: the codemod slice for each file's tree adds workspace or uuid arguments only, with assertions unchanged (criterion 7), and RK2 rewrites 1C's skip tests. Any other file Phase 1 adds is found the same way (question 23).

## Calvin ledger (report mode): author's answers

- **The ledger:** `calvin-ledger.md`, beside this design: 95 rows, from calvin in report mode on 2026-09-26. Its line numbers point into this design as calvin read it, kept as `work/calvin/design-before-calvin.md`.
- **What each answer changed** is named in its row. Every changed fact's other restatements in this design were swept in the same revision (the repo's half-swept-contract rule), and every code claim an answer adds is cited at `4a6373f0`.
- **The evidence** behind the answers is `work/calvin/*.out`, each beside the script that produced it.
- **For the user:** section 9's items 1 and 4 changed with these answers, and item 5 is new.

| # | Line | Quote | Category | Question | Status | Author's answer |
|---|------|-------|----------|----------|--------|-----------------|
| 1 | L8+L640+L647 | "All other lines: `4a6373f0`, which equals develop `77f06efb` outside 1A's files" | inconsistency · minor | Which commit pins each line number in section 8's table? L8 puts every line outside 1A's files at `4a6373f0`, L640 says the table's lines are the inventory's at `77f06efb`, and L647 marks four entity_server.py lines "at 4a6373f0", a file 1A changed. | RESOLVED | Every file:line the design cites is now at `4a6373f0`; inventory row ids are its only `77f06efb` references, since their lines live in the inventory. Two section 8 cites were `77f06efb` lines and are corrected: entity_server.py:679 to :688, and feature_lifecycle.py:566 to :593. Changed: the header's anchoring bullets, and section 8's lead-in. |
| 2 | L8+L689+L941 | "R2 re-anchors by symbol after Phase 1 merges" | assumption · minor | When is R2 written, relative to Phase 1's merge and to 4B's landing? L8 and L689 have R2 re-anchor "after Phase 1 merges", and L941 has it check tests-67 to -69 "after 4B lands". Who does that work if R2 is finished before either lands? | RESOLVED | R2 may be written before Phase 1 or 4B lands, so neither job waits on R2. Each RK task re-anchors its rows by symbol on its own branch before editing (the plan's anchor rule, plan:71), and the first RK task cut after 4B lands checks tests-67 to -69; until then they stay out, and Phase R's rebase re-checks. Changed: header, questions 23 and 25, section 14's Out list, section 15's task rule. |
| 3 | L12+L13 | "the inventory, `agent_sandbox/2026-09-26/rekey/inventory.md` and `inventory.json`" | completeness · minor | Once this design is copied into docs/plans/, how does a reader re-check what it cites (inventory rows, census and prototype keys, the `work/` scripts), when all of it sits in the gitignored agent_sandbox, and plan:255 names `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-inventory.md` as the inventory's home? | RESOLVED | The inventory's home is plan:255's `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-inventory.md`: the orchestrator copies it there with this design, and the design now names that path. The evidence (`work/`, the census and prototype keys) stays in the gitignored sandbox, cited by absolute path, as the plan's evidence rule says (plan:49-50). Changed: the Inputs and evidence bullets. |
| 4 | L25 | "classes of `workflow_phases` rows (section 5.1)" | inconsistency · minor | How does a reader tell row class W1 (L344) from rev 2.1's workstream W1 (L7, L788, L1067), or event class P1 (L156) from the plan's priority P1 (plan:237), when a line such as L400 ("exercised W3 and W7") or L679 ("class W4/W5") names one bare? | RESOLVED | The design's own class labels are renamed to what they mean. Row classes: matched, null-uuid, stale-uuid, archived, soft-deleted, shared, re-attached (new, row 33) and unmappable. Event classes: sole-holder, label-decided, undecided and no-holder. The queries follow (Q-rows-kept, Q-keys, Q-attributed, Q-audit and the rest). W1–W5 now only mean rev 2.1's workstreams, and P0–P2 the plan's priorities. Changed: names list, 3.3, 4.4, 5.1, 5.2, questions 9 and 15, 13.3, and section 14's Deferred table. |
| 5 | L32+L634 | "I1's correction" | ambiguity · minor | What is "I1's correction": where is it written, and which of its words say that problem 1 needs both halves? | RESOLVED | It is correction 1 of I1's report (`agent_sandbox/2026-09-25/release-c-followups/I1/report.md:15`, upheld by `I1-verify/verdict.md:13`): keying `workflow_phases` per workspace "is necessary but not enough", because "entity not found" comes from unscoped `get_entity(type_id)` calls. 1.1 and section 8 now cite and quote it. |
| 6 | L36 | "live, 5 type_ids are held by two workspaces" | inconsistency · minor | How do L36's "5 type_ids are held by two workspaces" and L15's "the seven shared type_ids" fit together? | RESOLVED | Census on the live copy: 7 type_ids are held by more than one workspace. Five have one row each, pedantic-drip's; `feature:035-slim-watchdog-self-mgmt` (both holders archived) and `project:P001` (three holders; projects get no rows) have none. 1.1 now says so. |
| 7 | L45–L47+L636–L638 | "34 survive Phase 1 (6.1)" | ambiguity · minor | Which document does each bare section number point into? In L45–L47 and L636–L638, "(6.1)" to "(6.4)" name the inventory's sections, while L24, L64 and L115 use the same numbers for this design's own 6.1–6.4. | RESOLVED | Each bare number in 1.1 and section 8 now reads "inventory 6.1" to "inventory 6.4"; a bare 6.x means this design's own section. |
| 8 | L47 | "Seven lookups settle a shared type_id seven ways" | inconsistency · minor | How many distinct ways are there, when inventory 6.4's table (the source L47 cites) shows three of the seven lookups taking the lowest rowid, and L43 says W2.1 already refuses one of them at `4a6373f0`? | RESOLVED | Five ways, not seven: raise "Ambiguous", answer None, take the lowest rowid (three lookups at `77f06efb`), answer only when the namesakes agree, or take the smallest workspace. At `4a6373f0`, W2.1 makes `create_workflow_phase`'s lookup refuse, which leaves two on the lowest rowid. 1.1 corrected. |
| 9 | L48+L634 | "that write cannot happen, so the two halves land together" | reasoning · minor | The re-key makes scoping the reads safe. What makes it necessary in the same round: what goes wrong for a user if the re-key lands and the unscoped reads wait? | RESOLVED | 1.1 gains the converse. Left unscoped, `get_entity` answers None for both namesakes, so the second workspace's feature stays "not found" even with its own row (I1's correction 1); and once writes go by uuid, `resolve_ref`'s lowest-rowid match could send a caller in B to A's row. Scoping without the re-key is unsafe; the re-key without scoping leaves problem 1 open. |
| 10 | L62 | "No SQL in the scan roots keys either table by type_id alone." | inconsistency · minor | How does this bar hold beside L769–L771, which allow migration functions, `cmd_merge_entities` and `display._rename`, all inside the scan roots, to key the tables by type_id? | RESOLVED | The bar now reads: outside the guard's declared allow-list (section 11), which holds the historical migrations and at most two named functions while they last. |
| 11 | L65+L803 | "Test: `test_mini_spec_of_a_is_invisible_to_b`." | completeness · minor | Which task writes `test_mini_spec_of_a_is_invisible_to_b` and `test_upsert_writes_own_row_leaves_namesake_unchanged` (L803)? Neither appears in a section 10 row or in any RK task's test list. | RESOLVED | Both are now in section 10 (criterion 1 holds the upsert test; criterion 4 holds the mini-spec test, as the 1.2 bar's item 3), in named files (`test_rekey_identity.py`, `mcp/test_rekey_event_streams.py`), and in RK2's red-first list. Each is red on RK1's head for a behavioural reason: upsert refuses today, and `get_mini_spec` reads both namesakes' events. |
| 12 | L68 | "All 529 rows keep their exact content." | ambiguity · minor | Which columns make up a row's "exact content", when the migration drops `type_id`, `workspace_uuid` and `uuid` from every row (L262–L264)? | RESOLVED | "Exact content" meant the six state columns plus the workspace and type_id the row belongs to, now read through the key; Q-rows-kept compares those eight values per row. The dropped `uuid` copy is checked separately: every non-NULL stored uuid becomes the key (Q-stale-uuid, 521). 1.2's item 5 is reworded. |
| 13 | L88+L649+L680 | "The dark v2 core declares `type_id` not unique (schema_v2.py:64, FR-4)" | ambiguity · minor | What does "dark" mean in "the dark v2 core" (L88), "Dark engine paths" (L649) and "Dark and test-only sites" (L680), and what is FR-4? | RESOLVED | Defined in the names list. Dark means shipped with no production path. The dark v2 core is `schema_v2._CORE_DDL` ("Ships dark", schema_v2.py:1-8; `type_id` "NOT unique (FR-4)", :64). FR-4 is feature 118's "No uniqueness constraint on any human-readable field" (`docs/dev_artifacts/workitems/118-uuidv7-identity-migration/spec.md:9`). The dark engine paths are the test-only engines-13 to -16. |
| 14 | L88+L121 | "C breaks the day that lands" | assumption · minor | What shows that the dark v2 core's non-unique `type_id` will ever reach a live file? And which of L119–L123's reasons for A still stand if it never does? | RESOLVED | Nothing shows it will: nothing schedules it, and production files keep `UNIQUE(workspace_uuid, type_id)`. C's cell now says C "would break if that ever reached a live file". If it never does, A still stands on criterion 3 by shape, the v2 key and the counted price; only the "survives FR-4" bullet depends on it, and that bullet now says the choice doesn't rest on it. |
| 15 | L89 | "a trigger cascade repeats `update_entity`'s drop and recreate of `enforce_immutable_workspace_uuid`" | ambiguity · minor | What would option B's trigger cascade repeat: which trigger gets dropped and recreated, by which code? And why does that count against B? | RESOLVED | The trigger is `enforce_immutable_workspace_uuid`. Every re-attributing writer drops it, writes, and recreates it (`update_entity`, database.py:8755-8805; `backfill_project_ids`, :8928; `claim_unknown_entities`, :9214). A trigger-based B would run its cascade inside that sequence in each writer, and a failure between the drop and the recreate leaves a guard missing (hence `update_entity`'s best-effort recreate, :8795-8805). B's cell now says so. |
| 16 | L91+L119 | "The only residue is a join through `entities` filtered by type_id alone, which the guard catches" | reasoning · minor | L91 has the guard catch A's one residue path, the same catch it calls "Discipline only" for B and C. What makes criterion 4 hold "by the schema's shape" for A (L119)? | RESOLVED | It doesn't, fully: that residue is guarded exactly as B and C are. Under A, criterion 3 holds by shape; criterion 4 holds mostly by shape (no type_id column to key by), plus the same guard for joins through `entities`. The A cell now says "Mostly structural", and 2.4's first reason is restated. The choice stands on criteria 2, 3 and 6. |
| 17 | L115 | "which is ten times larger than the key choice's difference" | vagueness · minor | Which two figures give "ten times", when L114 puts the key choice's difference at about 53 test statements and L695 puts the naming rule's churn at about 1240 test and 99 production edits? | RESOLVED | The figures were loose. 2.3 now compares the naming rule's churn, about 1430 calls (6.4, as re-estimated for row 47), with the key choice's difference of about 53 test statements: some 25 times larger. |
| 18 | L123+L264 | "which only ever held the entity's uuid" | inconsistency · minor | How does "only ever held the entity's uuid" (L123, L264) fit class W3 (L346), a stored `uuid` that disagrees with the matched entity, which the migration audits? | RESOLVED | It stated the live fact as a rule. On the live file every non-NULL stored uuid equals its matched entity's (521 of 521, Q-stale-uuid), but nothing enforces that, which is why the stale-uuid class exists. 2.4 and 4.2's dropped-objects table now say "an unenforced copy". |
| 19 | L123 | "the key W3.1 already exposes in list results (design:335)" | ambiguity · minor | What does "already exposes" refer to? At `4a6373f0`, `list_workflow_phases` joins on `type_id` alone and selects no `entity_uuid` (database.py:10460), and 2B, which would have added it, moved into Phase R. | RESOLVED | It referred to rev 2.1's W3.1 plan (design:334), which never landed: at `4a6373f0`, `list_workflow_phases` selects no `entity_uuid` (database.py:10454-10460). 2.4 now says the key W3.1 "planned to expose", which Phase R delivers. |
| 20 | L129 | "Criterion 4 covers it:" | reasoning · minor | The guard is this design's own (section 11). What in plan criterion 4's text (plan:261), which speaks of "another workspace's row" and "the table", reaches `phase_events`? | RESOLVED | Nothing does: plan criterion 4 names `workflow_phases`, and plan:271 leaves `phase_events` to this design. 3.1 now says the design extends criterion 4's rule to `phase_events`, because reading another workspace's events is the same hazard. |
| 21 | L137–L139 | "The cost is small:" | completeness · minor | L138–L139 count one ALTER, two UPDATEs and the readers. How many `append_phase_event` callers change with the new column and the "unknown entity raises" rule (L529), and are they inside 6.4's 99? | RESOLVED | Ten production call sites, listed in 3.1. Each already passes a `workspace_uuid` argument, so none changes for the column, and the unknown-entity rule only refuses a writer whose entity doesn't exist. They sit outside 6.4's 99, since the count skips every call that passes `project_id`. Tests: 55 calls pass neither `workspace_uuid` nor `entity_uuid` (`calvin/churn_gaps.out`), now part of 6.4's estimate. |
| 22 | L146+L525 | "its workspace's legacy id, when the event was written" | inconsistency · blocker | Which value does `append_phase_event` store in `project_id`? L146 says the entity's workspace's legacy id, and L525 says `project_id` "as passed". And what does it store for the 7 of 21 workspaces with no legacy id (L135)? | RESOLVED | As passed: it is a label, never resolution input. Most writers pass the entity's workspace's legacy id, or `'__unknown__'` for the 7 workspaces with none (`_resolve_project_id`, workflow_state_server.py:895-918; an entity dict's `project_id` is `w.project_id_legacy`, database.py:8236). `issue_spawn` passes its own server's label, even for a parent in another workspace (entity_server.py:966-970). 3.2 and 6.3 now say the same thing. |
| 23 | L146–L148 | "stay, as write-time labels:" | reasoning · minor | What is each label for once nothing filters on it (L536)? Who reads `project_id` after the re-key, and what is lost without it? | RESOLVED | `type_id`: the only identity of the 25 unattributed rows, display, and a later repair's input. `project_id`: the evidence the label-decided class uses (8 rows) and a later repair would. After the re-key no production code filters or joins on either; `rebuild_tool`'s event copy (rebuild_tool.py:1015-1072), today's one reader that maps a label to a workspace, maps `entity_uuid` instead. Without the label, that evidence is lost. Added to 3.2. |
| 24 | L147 | "Never read as keys:" | completeness · minor | Which guard rule flags SQL that keys `phase_events` by its `type_id` label while the same string holds an `e.workspace_uuid` predicate, when rule 1 (L744–L746) flags only strings with no `workspace_uuid` predicate? | RESOLVED | None did. Rule 1 gains a labels clause: in a string that names `phase_events`, any predicate on that table's `type_id` or `project_id` is flagged, whatever else the string holds, including a workspace predicate on `entities`. |
| 25 | L148 | "the table is an append-only history" | ambiguity · minor | What does "append-only" mean here, when the migration UPDATEs rows' `entity_uuid` (L408–L420), L170 allows a later repair to UPDATE them again, and L942 names a script that UPDATEs `phase_events.phase`? | RESOLVED | The wrong word. 3.2 now says the table is a history whose labels are never rewritten. The one update this design allows sets a NULL `entity_uuid` once (the migration, a later repair), which `enforce_immutable_pe_entity_uuid` enforces; SCR-11's rewrite of `phase` was a one-off at the v2 cutover. Criterion 3's row in section 10 follows. |
| 26 | L156+L159 | "The type_id decides, since only one entity anywhere holds it." | reasoning · minor | What shows that each of the 356 P1 events whose label names another workspace or none belonged to today's sole holder, and not to an entity that held that type_id when the event was written? L159 says backlog type_ids were "renumbered away". | RESOLVED | Checked now. Across the 19 registry backups (the oldest from 2026-03-23), none of the 74 type_ids behind the 356 events was held under another name; uuids differ only across the 2026-07-25 cutover's re-mint, with the same names (`calvin/p1_holder_history.out`). No type_id has two `entity_created` events. The limit stays stated: an event older than the oldest backup can't be checked this way. Added to 3.3's evidence. |
| 27 | L575+L229+L595+L923 | "an orphan row can no longer exist" | assumption · minor | L575, L595 and L923 rest on orphan rows being impossible. What keeps a row from outliving its entity on a connection with foreign keys off, when L229's refusal needs foreign keys on and `wp_reject_unknown_entity` fires only on INSERT (L218–L221)? | RESOLVED | Nothing does, fully. "Can no longer exist" becomes "pd's code can no longer create one": no pd code hard-deletes an entity (`delete_entity` soft-deletes, database.py:9087), and every `EntityDatabase` connection has foreign keys on (database.py:11074). A raw-SQL hard delete with foreign keys off can still leave one, so the doctor's orphan check stays, re-keyed to report `foreign_key_check` rows with no fix; only the auto-fix goes. Changed: 4.2, section 7, question 14, section 12, section 14, RK2. |
| 28 | L235 | "altered in place (no copy-rename" | inconsistency · minor | How does altering `phase_events` in place meet plan criterion 5's "uses the copy-rename pattern with `foreign_key_check`" (plan:262)? | RESOLVED | Criterion 5's copy-rename is for the table whose key changes, which SQLite can't alter in place: `workflow_phases`. `phase_events` keeps its key and gains only a nullable column, which ADD COLUMN adds in place, and both tables pass `foreign_key_check`. 4.2 now states this reading of the criterion. |
| 29 | L274–L282 | "Open question 11: the `entity_axis_state` text" | reasoning · minor | What goes wrong if `entity_axis_state` keeps its live text this round, when L282 finds no production reader? Why does the re-key carry this change? | RESOLVED | Nothing user-visible, since no production reader exists. It is carried because criterion 5's one target covers the whole schema: left alone, the live file would differ from every staging file in one object, and a later fix would need its own version bump and live migration. Added to 4.3. |
| 30 | L280 | "The live text was never committed:" | reasoning · minor | How do you know the live view text was never committed? Which search of the history shows it? | RESOLVED | `git log --all -G "to_value IS NOT NULL"` over views.py prints nothing, and the phrase occurs in the history only in `cbee6257`, whose migration 3 rebuilds the view from `_VIEWS_DDL`, and in `e01ec8f0`, a docs commit (`calvin/view_text_history.out`). Added to 4.3. |
| 31 | L296 | "a peer may have finished first" | completeness · minor | When the re-probe under the lock finds nothing pending, what ends the transaction that step 3 opened, and what does the function return? | RESOLVED | `ROLLBACK`, since nothing was written; restore `foreign_keys` in the `finally`; return None; write no audit row. 4.4's step 4 now says so. The prototype, which writes an empty success row there, is not the contract. |
| 32 | L344–L350 | "matched: an entity holds the row's `(workspace_uuid, type_id)`" | ambiguity · minor | Are the classes of L344–L350 disjoint? W1 counts all 529 rows while W2, W4 and W6 count rows inside them. What does the "Live rows" column add up to? | RESOLVED | They are not disjoint. Matched, re-attached and unmappable partition the rows (529 + 0 + 0 live); the other five classes are facets inside matched, so the column doesn't sum. A note under the table says so. |
| 33 | L350+L353+L38 | "a NULL-workspace row is a pre-migration-11 orphan" | completeness · blocker | L38 says `backfill_project_ids` and `claim_unknown_entities` re-attribute entities without touching their rows. What should the migration do with such a row, whose `(workspace_uuid, type_id)` no entity holds but whose stored `uuid` still names its entity? L350 drops it, and L353's reason covers only NULL-workspace rows. | RESOLVED | A real gap. A new class, re-attached: the pair matches nothing, but the stored `uuid` names an entity that no row matches by pair and that no other row's `uuid` names. Such a row is copied, keyed by that uuid, and audited as `rekey_row_reattached`; only the rest is dropped. The SQL is in 5.1, checked on a synthetic file (`calvin/reattach_probe.out`); the live copy has 0 such rows. Changed: 4.4's step 6, 5.1, Q-unmappable, Q-audit, 13.5, criterion 5's test name. |
| 34 | L440–L441 | "one 'success' row" | completeness · minor | Q-A matches on `payload LIKE '%rekey_workflow_phases%'`. Do the payloads of the `rekey_row_dropped` and `rekey_stored_uuid_ignored` rows match too, and how many rows does Q-A return on a file that has them, such as the class fixture? | RESOLVED | The prototype's per-row payloads don't carry the name, so Q-A returned one row there, but the design didn't pin that. Now every audit row carries `"migration": "rekey_workflow_phases"`; Q-audit filters `event_type = 'success'` (exactly one row), and Q-audit-rows counts the per-row events (none live; one per seeded case on the class fixture). |
| 35 | L447+L448 | "(both holders archived, no rows)" | completeness · minor | L447 says the startup backfill seeds rows for archived entities too. What rows does `feature:035` get once W2.6's backfill runs in pedantic-drip or terry_agent, before or after the migration, and do section 13.5's figures assume it has not run? | RESOLVED | Before the re-key, the first workspace whose server backfills seeds its 035 a row, and the other's backfill skips, because the row check is unscoped (backfill.py:277, :339). After RK1 and the migration, each workspace's backfill seeds its own namesake. 13.5's figures are the migration's, taken before any server starts; step 7 adds what the backfill reports. Changed: 5.3, 13.5. |
| 36 | L452 | "the Deferred table in section 14" | inconsistency · minor | Where is the five namesakes' Deferred row? L952–L958 hold none, and L947 lists them under "Out". | RESOLVED | There was none. Section 14's Deferred table now holds it; it reopens when the user rules on re-attributing or archiving them. |
| 37 | L459 | "One rule covers every `EntityDatabase` method that names one entity." | completeness · minor | Which methods are those? Is 6.3's table the whole list, and where is the list pinned so a reader can check it? | RESOLVED | Now pinned: `ENTITY_NAMING_METHODS` lists 20 (method, parameter) pairs, written out in 6.3's lead-in, and the guard's AST scan (section 11) checks the list complete. 6.3's table covers all of them; `resolve_entity_uuid` was missing and is added. |
| 38 | L465 | "A uuid names an entity in any workspace." | ambiguity · blocker | What happens when a caller passes a uuid together with a `workspace_uuid` that is not that entity's workspace? Which one decides, and is the write that follows a "silent cross-workspace write" in plan:218's sense? | RESOLVED | The uuid decides: the uuid branch returns before it reads any workspace (database.py:7017-7024), today and after. It is not a silent cross-workspace write in plan:218's sense: the caller named that one entity by its identity, as D5 allows, while plan:218's hazard is a type_id reaching a namesake's row. Pinned in 6.1, with a keep-green test, `test_uuid_resolves_its_entity_whatever_the_workspace`. |
| 39 | L466 | "or the deprecated `project_id` alias on the methods that already accept it" | ambiguity · blocker | Which workspace does the alias name when `project_id` is `__unknown__`, `'*'`, or a legacy id that no workspaces row holds? `_resolve_optional_workspace_filter` (database.py:6896) maps the first to the unknown workspace and raises for a label with no row. | RESOLVED | Exactly as `_resolve_optional_workspace_filter` does (database.py:6896-6977): `'__unknown__'` names the unknown workspace; another value names the workspace whose `project_id_legacy` it is, or raises `ValueError`; given both, `workspace_uuid` wins. `'*'` is not a workspace: list and export tools map it to "no filter" before calling the library (entity_server.py:1183, :1226, :1426; workflow_state_server.py:2451-2493), and as an entity's workspace it raises. Added to 6.1. |
| 40 | L522+L466+L529+L50 | "It resolves the entity once: by `entity_uuid`, or by the rule." | assumption · blocker | L50 says the `project_id` label names the holder's workspace for only 1088 of 1469 live events. Once `append_phase_event` resolves its entity through that same alias whenever no `workspace_uuid` is passed, what do the writers that produced the other labels pass, and what happens to their writes (L529)? | RESOLVED | `append_phase_event` takes no alias: its `project_id` is the label (6.1, 6.3). It resolves by `entity_uuid`, or by `type_id` with `workspace_uuid`. Every production writer already passes a `workspace_uuid` (3.1), so each write resolves by it, never by a label that names another workspace for 381 of the 1469 live events. |
| 41 | L469+L504 | "so no workspace still means every workspace" | inconsistency · minor | How do L469's rule for searches and L504's `search_by_type_id_prefix`, whose workspace "becomes required", fit together? | RESOLVED | `search_by_type_id_prefix` is not a list: its only production caller is `resolve_ref`, whose answer names one entity, so it follows the rule. 6.1 now says so, and its list of legal all-workspaces calls adds `search_entities`. |
| 42 | L492 | "any reader it missed fails loudly with a `KeyError`" | reasoning · minor | The grep looked for `["uuid"]` reads. What does a reader that uses `.get("uuid")`, or a template that reads `item.uuid`, do once the key is gone? | RESOLVED | Checked: no `.get("uuid")` read or template `.uuid` read is on a workflow-row result at `4a6373f0`; each is on an entity or workspace dict (`calvin/uuid_reads.out`). Such a reader would get None or an empty string silently, so 6.2 no longer claims it would fail loudly, and RK2's reviewer re-runs both greps. |
| 43 | L505 | "pass the workspace they are given" | completeness · blocker | Where does each get a workspace? At `4a6373f0`, `feature_dir_name(db, artifacts_root, type_id)` (feature_paths.py:71–73) and `engine._feature_dir_name(self, feature_type_id, *, use_db=True)` (engine.py:385–387) take none. Which of their callers change? | RESOLVED | They get one. `feature_dir_name`, `feature_dir_path` and `engine._feature_dir_name` gain a keyword `workspace_uuid`, used only when they read the registry, and their callers pass the one they hold, listed in 6.3's row (engine.py:140, :250; feature_lifecycle.py:133 through :591; task_promotion.py:327; workflow_state_server.py:442; reconciliation.py:208 through :229, :747 and :750). The `use_db=False` calls need none. |
| 44 | L506+L758 | "same signatures" | completeness · blocker | L758 builds `ENTITY_NAMING_METHODS` from the public methods whose first parameter is `ref`. L506 keeps `set_parent`, `get_lineage`, `reparent_entity` and `export_lineage_markdown` on signatures whose first parameter is `type_id` (database.py:7943, :8099, :8346, :9367), and `append_phase_event` and `query_phase_events` name entities by keyword. Which refusal test covers them? | RESOLVED | None did. `ENTITY_NAMING_METHODS` becomes declared (method, parameter) pairs, and its completeness check scans for every parameter named `ref`, `type_id`, `parent_type_id` or `prefix` of a public method: 21 pairs at `4a6373f0`, 20 after. The refusal test covers each pair: `set_parent` once per parameter, `append_phase_event` with a label and no workspace, and `get_lineage`, `reparent_entity`, `export_lineage_markdown` and `query_phase_events` by their `type_id`. |
| 45 | L502–L514 | "first parameter becomes `ref`" | completeness · blocker | Which RK task renames the first parameter to `ref` on the methods L502–L514 list? RK1 (L969–L971), RK2 (L991–L998) and RK4 (L1042–L1045) name none of the renames. And what happens to callers that pass `type_id=` by keyword? | RESOLVED | None needs to: the renames are dropped. The rule applies to the value passed, whatever the parameter is called, so every method keeps its parameters, keyword callers such as `type_id=` are unaffected, and no task has renames to make. 6.3's rows now say "same signature". |
| 46 | L517 | "`type_id` becomes optional when `entity_uuid` is given" | ambiguity · minor | When a caller passes both `entity_uuid` and a `type_id` that is not that entity's, what does `append_phase_event` do, and which `type_id` does it store as the label (L524)? | RESOLVED | It checks them: an `entity_uuid` with a `type_id` that is not that entity's raises `ValueError`, and given `entity_uuid` alone, the label is the entity's type_id. Added to 6.3. |
| 47 | L540 | "The count is an upper bound" | reasoning · minor | What makes 99 and 1240 upper bounds, when `churn_totals.py` counts calls to a fixed method list and skips every call that passes `project_id` or `entity_uuid`? Which calls could it miss entirely? | RESOLVED | Nothing: it isn't a bound. 6.4 now calls it an estimate. It over-counts uuids passed through neutral names or by keyword, and MCP tool functions named like library methods; it misses 55 test `append_phase_event` calls (skipped for passing `project_id`), the feature-directory helpers (15 production and 23 test calls) and calls through `getattr` (`calvin/churn_gaps.out`). The estimate becomes about 115 production and 1320 test calls, swept into 2.3, section 9 and RK4. |
| 48 | L548 | "Each fixture already registers its entities in a known workspace" | assumption · blocker | How do you know every fixture registers its entities in one known workspace? And what does the codemod add to a call in a test that registers entities in two? | RESOLVED | I didn't know it. Registration requires a workspace (database.py:7679-7680), so each test entity's workspace is written in its test, but 29 of the 77 test files that register entities use more than one workspace expression (`calvin/codemod_workspace_scopes.out`). The codemod now works per test function: with one expression in scope, it adds it; with two or more, or none it can read, it lists the calls for hand edits. A call that names two workspaces' entities passes their uuids. |
| 49 | L553+L563–L564 | "never the legacy label" | inconsistency · minor | How does "never the legacy label" fit L563–L564, where `query_phase_analytics` keeps `project_id='*'` and `_effective_project_id()` survives as the filter of list and export tools? | RESOLVED | 6.5 is narrowed. For a call that names an entity, the servers hand the library a workspace uuid, never the label. Lists, searches and exports, which name no entity, may still pass the label or `'*'` as a workspace filter, which the library resolves and never compares with a label column. |
| 50 | L555–L561 | "write tools, which W4.1 already covers, and read tools:" | completeness · minor | Is this list meant to be complete? `validate_prerequisites` (`feature_type_id`, `ref`) and `reconcile_frontmatter` (`feature_type_id`) name an entity at `4a6373f0` (workflow_state_server.py:2411, :2592) and are not in it. | RESOLVED | It wasn't; now it is, from an AST scan of the tool definitions at `4a6373f0`, less W1's `reconcile_apply`. It adds `validate_prerequisites`, `reconcile_frontmatter` and `query_phase_analytics`' `feature_type_id` filter, and, on the entity server, `get_entity_tags` and `get_okr_alignments`. |
| 51 | L562+L565 | "scope to `_require_workspace()` as well (open question 7)" | ambiguity · blocker | Once the three list tools scope to `_require_workspace()` and keep their parameters (L565), what does their `project_id` argument do? | RESOLVED | It keeps today's meanings (workflow_state_server.py:2451-2493): `'*'` lists every workspace, as an explicit opt-in, and a legacy id lists its workspace or answers `invalid_project_id`. Only the omitted case changes, from `_workspace_uuid or None` (:2493) to `_require_workspace()`, and that change is itself now for the user (row 68). 6.5 updated. |
| 52 | L565 | "so no command or skill markdown changes (open question 6)" | reasoning · minor | Which command or skill markdown depends on the behaviour L562 and L567 change (all-workspaces lists, or reaching a type_id another workspace holds), given that the inference rests on parameters and replies alone? | RESOLVED | Checked. The markdown callers (`create-feature.md:12`, `list-features.md:11`, `workflow-state/SKILL.md:10`) omit `project_id` and never pass `'*'`; the one change they can see is the `workspace_unresolved` envelope in a session whose workspace is unresolved, which `list-features.md` already surfaces verbatim (:15). No markdown passes another workspace's type_id. Added to 6.5. |
| 53 | L597 | "With no workspace selected, a type_id answers the 404 page, since every rendered link is a uuid." | completeness · minor | Who still reaches `/entities/<type_id>` once every rendered link is a uuid? And what do they get in the board's default all-workspaces view (L584)? | RESOLVED | Only a URL typed or saved by hand. In the board's default all-workspaces view it answers the 404 page, never another workspace's namesake; with a workspace selected, it resolves there. Added to section 7. |
| 54 | L641+L651 | "Every other row changes by passing a workspace its caller already has." | inconsistency · minor | How does "a workspace its caller already has" fit L651's CLIs, which resolve one first and skip when it stays unresolved? And what does a user lose when one of them skips? | RESOLVED | Reworded: every other row passes a workspace its caller has, or, for the CLIs, resolves one once from the project root and skips when that fails. On a skip, the user loses that run's effect for that feature (the injected frontmatter, the synced field, the parent-context line), and nothing is written to another workspace. Section 8 updated. |
| 55 | L648 | "The read paths gain it" | ambiguity · blocker | What does an engine read path do when its caller passes no workspace? And which contract governs the engine methods 6.4 counts (9 production and 132 test calls)? | RESOLVED | The library's contract. An engine method that takes a type_id also takes `workspace_uuid`, and passes it to every library call it makes. With a type_id and no workspace, the library's `ValueError` propagates: the engines catch only `sqlite3.Error` for their `.meta.json` fallback (`get_state`, engine.py:91-111), so a missing workspace is never answered from a file. Before RK4 the fallback still answers. Added to section 8's engines row. |
| 56 | L677+L678+L680+L682+L836 | "the C23 guard makes an old build read-only on the version-8 file" | ambiguity · minor | What are C23 (L677, L836), C8 (L678), 5D (L680) and C22 (L682), and where does a reader of this document find each one defined? | RESOLVED | Defined in the names list. C8, C22 and C23 are Release C contracts in `docs/dev_artifacts/plans/2026-09-20-display-id-ownership-implementation.md` (:328-334, :412, :425). 5D is the five-phase sequence `FiveDBackend` runs for L1, L2 and L4 entities (entity_engine.py:9, :106). |
| 57 | L678 | "if W1 leaves it" | vagueness · minor | Who checks whether W1 leaves C8's orphan `db_only` branch, and at which point? | RESOLVED | RK2's implementer, before editing, on the landed Phase 1 code. The task report records whether W1 left it, and if it did, RK2 deletes it with its tests. Question 14 and RK2 now say so. |
| 58 | L694 | "Each item has a recommendation, and the playbook follows it unless the user rules otherwise." | completeness · minor | When, and through whom, does the user see these four items? And what does the playbook do meanwhile with item 1's 1240 test edits? | RESOLVED | The orchestrator asks section 9's items through AskUserQuestion after R3's verification and its one revision, before R4 starts. RK1 to RK3 don't depend on any answer and may start; RK4 waits for item 1, and RK5's inventory for item 2. Added to section 9. |
| 59 | L696 | "Criterion 4 needs the library itself to refuse a type_id with no workspace (6.1)." | ambiguity · minor | What does plan criterion 4's "enforced by the API's shape" (plan:261) mean, and what in it requires the library itself to refuse at run time? | RESOLVED | The plan's words don't require a run-time refusal; that is this design's reading of them. Python can't make `workspace_uuid` required only when the value passed is a type_id, so "the API's shape" is enforced where every method resolves: `_resolve_identifier` refuses. Section 9's item 1 now says so. |
| 60 | L698 | "A process that serves several workspaces (the UI server, the session-start orchestrator)" | reasoning · minor | Which workspaces does the session-start orchestrator serve in one process, when plan F1 runs it with one `--project-root` and one pinned workspace per step (plan:376, plan:388)? | RESOLVED | It doesn't: the orchestrator serves one workspace per run. The examples are now the UI server, which serves one workspace per request, and a test session whose fixtures register several workspaces on one connection. |
| 61 | L705+L878+L1059 | "The yes also covers the publish that must follow it in the same sitting (13.2)." | ambiguity · blocker | How many yeses does RK6 need? L705 says the migration's yes "also covers the publish", while L878 publishes "on F3's publish yes". | RESOLVED | One. RK6's F3 question asks to land Phase R, migrate and publish, in one sitting, and the publish runs under that same yes. Section 9's item 4, 13.3 (precondition 3 and step 6), RK6 and section 12's plan changes now say so. |
| 62 | L713 | "`test_rekey_schema.py` and `test_rekey_migration.py` go in `plugins/pd/hooks/lib/entity_registry/`, under G1" | completeness · minor | Which files hold `test_naming_rule.py`, the criterion-2 and criterion-3 tests and `test_rows_join_entity_phase_status_one_to_one`, and which gate collects each? | RESOLVED | Section 10 now maps every named test to a file, each collected by G1: `test_rekey_schema.py`, `test_rekey_migration.py` (which holds `test_rows_join_entity_phase_status_one_to_one`), `test_rekey_identity.py` (the behaviour tests of criteria 1 to 3), `test_naming_rule.py`, `mcp/test_rekey_event_streams.py`, `ui/tests/`, and the guard's file. |
| 63 | L721+L777–L778+L1055 | "which detects 25 sites on today's code" | inconsistency · minor | How many sites does the guard detect today? L721 and L1055 say 25, while L777–L778 add 5 rule-3 sites and 4 rule-4 links to the 25 of rules 1 and 2. | RESOLVED | 34: rules 1 and 2's 25 SQL functions, 5 Python sites and 4 template links, each now with its task. Swept: section 10's criterion 4, section 11's measured list and site list, and RK5's rows. |
| 64 | L744–L746+L469 | "has no `workspace_uuid` predicate" | assumption · minor | How does rule 1 tell an all-workspaces list or search, which L469 keeps legal, from a type_id-keyed access, when both can hold a `type_id` predicate and no `workspace_uuid` predicate? | RESOLVED | By construction after the re-key: a type_id predicate names an entity, so any string that holds one must hold a workspace predicate. All-workspaces lists and searches filter on other columns (kind, status, phase, an FTS MATCH). The probe found no legal all-workspaces SQL with a type_id predicate once `feature_entity_id` is scoped (row 43). Added to rule 1. |
| 65 | L755 | "It flags a dict comprehension keyed by" | completeness · minor | Which other Python shapes key workflow rows by `type_id`, and does rule 3 see any of them? | RESOLVED | Set comprehensions, subscript keys, mapping lookups, `key=` lambdas and membership tests. Rule 3 now covers them all, and the extended probe finds the same five functions (`calvin/guard_rule3_extended.out`). Its limit is stated: it is function-local, so a helper that is handed rows by its caller is the reviewer's to check. |
| 66 | L773 | "at most 2 when RK5 lands, then 1, then 0" | vagueness · minor | Which events take the mark to 1 and then to 0, when L700 recommends keeping `cmd_merge_entities` and L958 reopens it only when "a cross-machine import is next needed"? | RESOLVED | To 1 when task 4A deletes `display._rename` (if 4A lands after RK5, its own change lowers the mark); to 0 only if merge-entities is fixed or deleted. Under the recommended keep, the mark stays at 1 until merge-entities' Deferred row reopens. Section 11 corrected. |
| 67 | L793+L1046 | "Feature 129's four tests are unchanged." | assumption · minor | Does RK4's codemod (L1046) touch any call inside feature 129's four tests? If it does, what does "unchanged" promise? | RESOLVED | Yes, two counted calls. `test_cross_workspace_matrix.py:307` calls the library's `set_parent` with a child and a parent type_id from two workspaces, so it must pass their uuids, by hand. `test_cross_workspace_mcp_regression.py:213` already passes uuids, to the MCP tool (`calvin/feature129_codemod_touch.out`). "Unchanged" meant their assertions, which W3.4 and the plan require (plan:235). Section 12 and criterion 7 now say so. |
| 68 | L797–L810 | "Superseded:" | assumption · blocker | Which ruling lets this design supersede rev 2.1's W2.1 text and tests (L801–L804) and W4.1's "Read tools keep today's behaviour" (L809), when the D3 record names only the Deferred rows and W3.1–W3.3 as what Phase R supersedes or absorbs (design:145–146, plan:45)? | RESOLVED | The D3 ruling (plan:44-45; design:143-147): it supersedes the Deferred rows for the re-key, the read-scoping and the type_id-only writers, and absorbs W3.1–W3.3. W2.1's column text, upsert refusal and row-column tests fall with the re-key's schema; W4.1's sentence falls, for read tools that name an entity, as read-scoping. The three list tools' default is not covered: it goes to the user (section 9, item 5), and without a ruling W4.1's text stands for them. Section 12 now states the authority. |
| 69 | L812–L818+L803 | "Plan changes this design needs." | completeness · minor | Plan:21 closes problem 3 when "every insert stores the resolved entity's `workspace_uuid` and `uuid`", checked by the "Upsert refuses" test that L803 retires. Which plan change restates that problem and its check? | RESOLVED | Added to section 12's plan changes. Problem 3 becomes "every insert is keyed by the resolved entity's uuid, and the row's workspace and type_id are the entity's, read by join", checked by the restated "Explicit workspace" test, `test_upsert_writes_own_row_leaves_namesake_unchanged`, `wp_reject_unknown_entity`'s refusal and F1 step 4. |
| 70 | L812–L818 | "R2 carries them into the plan and the playbook." | completeness · blocker | Once RK6 changes the live file, how do F1's "the live file's fingerprint matches kickoff's" (plan:408) and Done-when #4 (plan:437) hold at F2, and which of these plan changes covers them? | RESOLVED | Added to section 12's plan changes: after RK6, F1's live-fingerprint check (plan:408) and Done-when #4 (plan:437) compare against the fingerprint RK6 records after the approved migration (13.3, step 5), which replaces kickoff's from then on. |
| 71 | L817+L447 | "e.kind IN ('feature','brainstorm','backlog')" | inconsistency · minor | Which kinds gain rows in F1 step 4, when L447 says `backfill_workflow_phases` lists every entity of its workspace except projects? Does "exactly those entities gain rows" still hold? | RESOLVED | It didn't: the backfill seeds every kind except projects (backfill.py:246-247). The Before query now uses the backfill's own rule, `e.kind <> 'project'`. On today's data it selects the same entities, since the live file holds only backlog, brainstorm, feature and project entities. |
| 72 | L824+L829 | "Once RK2 is on develop" | ambiguity · minor | When does RK2 reach develop, given that the plan merges task branches into a phase branch and lands each phase whole (plan:66–69)? | RESOLVED | Only when Phase R lands whole (plan:66-69), and Phase R now lands only in the RK6 sitting, after the user's yes. So "once RK2 is on develop" is the sitting itself. 13.1 and section 12 say so. |
| 73 | L829 | "nothing from develop opens `~/.claude/pd/entities/entities.db`, and nothing is published" | assumption · blocker | What enforces this for the whole RK2→RK6 window, and how would anyone learn it was broken? The user works in the main checkout on develop (plan:59), and L826–L828 name scripts, the UI server and session hooks that open the file. | RESOLVED | The landing rule: develop and every publish hold no RK2 code before the sitting, and agents never open the live file (a temp HOME, plan:343-344; the safety rules, plan:103-112). In the sitting, preconditions 4 to 6 close every pd process and check that `schema_version` is still 7; an 8, or this migration's success row dated before the sitting, would show a breach. 13.1 and 13.3 updated. |
| 74 | L829+L705 | "between RK2 landing and RK6" | completeness · blocker | What happens to develop, to publishing and to the user's own pd use if the user declines RK6, or puts it off? How long can this rule hold? | RESOLVED | Phase R stays on its branch. Develop and every publish stay on version-7 code, and pd works as it does after Phase 1; problem 1 and the W3.1–W3.3 fixes wait with it. There is no deadline: each later landing makes Phase R rebase and re-run its integration QA (plan:74-75), and F2 records the deferral. Section 9's item 4 and section 12 say so. |
| 75 | L853+L894+L898+L905 | "the landed code (not this prototype) migrates the copy" | inconsistency · blocker | Which code does R3's rehearsal run, and when? L894, L898 and L905 require "the landed code" and "the landed build", L853 makes the rehearsal a precondition of RK6, and the plan runs R3 before R4 executes anything (plan:282–292). | RESOLVED | R3's own build: the playbook's changes on a scratch export of develop after Phase 1 (plan:284), since nothing of Phase R has landed when R3 runs. RK6's same-minute rehearsal re-runs 13.5's steps 2, 3 and 7 with the code about to land. 13.3 and 13.5 reworded. |
| 76 | L855+L1057 | "No process holds the file" | assumption · blocker | Who is RK6's operator, and how does "no process holds the file" hold when that operator's own Claude Code session runs pd's MCP servers against the live file? Plan:419 lets the user re-enable pd once Phase 1 is published. | RESOLVED | The orchestrator, in a Claude Code session started with pd disabled at user level, as it has been since 2026-09-24. If the user re-enabled pd after Phase 1's publish, the sitting starts with the user disabling it and restarting every session, the operator's included, since pd's MCP servers hold the file open. 13.3, precondition 4. |
| 77 | L856+L864 | "If it doesn't, the user's sessions have written the file since" | reasoning · minor | What else changes that fingerprint? And why does this procedure re-derive and carry on (L864) where F1 stops and asks the user on a changed fingerprint (plan:411)? | RESOLVED | Any writer: a pd session (its backfill, workflow tools and session hooks), a repo script run with the real HOME, a WAL checkpoint. A change since R3 is expected once the user has used pd, so the procedure records both fingerprints and the cause, and re-derives its figures. A change during the sitting stops it and goes to the user, as F1 does (plan:411). 13.3's preconditions 5 and 6, and step 3. |
| 78 | L864 | "the figure re-derived by the same rule from the backup" | completeness · minor | Which queries compute the re-derived expected figures from the backup (for example the P1 and P2 counts), and where are they written? | RESOLVED | Added to 5.2 as "Expected figures on any file": 5.1's pre queries and the re-attach SELECT for rows, and one query for the event classes, by the UPDATEs' own predicates. Checked on the prototype's backup: rows 529, 0 and 0; events 1436, 8, 13 and 12 (`calvin/live_class_counts.out`). The phase report records both sets of figures. |
| 79 | L885–L886 | "Remove a stale `-wal` or `-shm`, only if one is present and no process holds it." | reasoning · minor | Why copy first and remove second? What happens to a `-wal` that exists before the copy, and how is a "stale" one told apart? | RESOLVED | It shouldn't remove anything. The backup API writes through a SQLite connection, which reads any `-wal` the migrated file left and then overwrites every page. Step 3 now says never to delete a `-wal` or `-shm` by hand; if one remains after the connection closes, run `PRAGMA wal_checkpoint(TRUNCATE)` once. |
| 80 | L888 | "republish the last build from before Phase R" | completeness · minor | Which commit is "the last build from before Phase R", and from which checkout does `sync-cache.sh` publish it while the main checkout sits on develop (plan:59)? | RESOLVED | The develop commit just before Phase R's fast-forward, which 13.3's step 3 now records. `sync-cache.sh` publishes the checkout it runs in (sync-cache.sh:11-13), so it runs from a scratch clone at that commit while the main checkout stays on develop. The restore and the republish are one gated write, on the user's yes. 13.4 updated. |
| 81 | L889 | "Writes made between the apply and the rollback are lost." | completeness · minor | Once the new build has written to the migrated file for days, what recovery exists other than restoring and losing those writes? | RESOLVED | Roll forward: fix and publish, keeping the file. Restoring with loss is for the sitting, before any session writes; later it needs the user's explicit choice, with the changed rows listed for re-entry. 13.4's "When" now says so. |
| 82 | L905–L906 | "The board shows 366 cards across workspaces (529 with archived ones)." | assumption · minor | Which workspace do step 7's servers resolve, and does their startup backfill (W2.6) seed rows before the board is counted? Do 366 and 529 still hold then? | RESOLVED | Each run is pinned (`ENTITY_WORKSPACE_UUID`, as F1 pins), and its entity server backfills first: 28 rows in pedantic-drip and 6 in terry_agent, on today's data. The expected board is the migration's figures plus those: 391 cards, and 563 with archived ones. On a changed file, the counts the backfill reports replace these. 13.5, step 7. |
| 83 | L907+L447 | "A `transition_phase` and a `get_mini_spec` for each namesake answer from that namesake's own entity." | ambiguity · blocker | What should `transition_phase` answer for terry_agent's archived namesakes, which L447 leaves row-less until terry_agent's server backfills, and with which workspace pinned? | RESOLVED | Step 7 no longer asks `transition_phase` of them. Pinned to terry_agent, after its backfill seeds the namesakes' rows, `get_phase` answers from terry_agent's own entities, and the write check is `transition_entity_phase` moving its brainstorm namesake from draft to reviewing (router.py:203), with pedantic-drip's row fingerprint unchanged. `transition_phase` on the archived features is left out: its gates read feature directories the scratch setup lacks. |
| 84 | L935 | "found by grep in RK2 under the repo's sweep rule" | vagueness · minor | Which grep (what pattern, over which paths) finds "the docs that restate the key", and who checks that the result is complete? | RESOLVED | Pinned in section 14: the exact `git grep` (its pattern, over `*.md`, excluding the records: docs/plans, features, brainstorms, projects, rca, knowledge-bank, CHANGELOG and agent_sandbox). It prints 39 lines in 8 files at `4a6373f0` (`calvin/docs_key_grep.out`). RK2's report gives each line a disposition, and the task's reviewer re-runs the grep. |
| 85 | L945+L1070 | "R3's step 7 exercises that." | inconsistency · minor | Which hook runs in R3's step 7, when L905–L907 start only the two MCP servers and the UI? | RESOLVED | None did. Step 7 now also runs the Python the hooks launch, against the copy: the session-start orchestrator (HOOK-1), the doctor with `--fix` (HOOK-2) and `pd_state_diff.py` (HOOK-4). HOOK-5 is the UI that step 7 already starts, and HOOK-3 reads no registry. |
| 86 | L948 | "The re-key makes duplicates harmless for workflow rows and events." | vagueness · minor | What does a duplicate type_id still cost a user after the re-key, outside workflow rows and events? | RESOLVED | Two items with one type_id in all-workspaces views, a type_id URL that needs a workspace selected, and SCR-4's cross-workspace write, which has a Deferred row. Section 14 now says so. |
| 87 | L962+L688 | "so G1–G5 stay green at every merge" | reasoning · minor | How do you know G1–G5 stay green at every merge, when L688 says this design's prototype ran "no test suite"? | RESOLVED | I don't yet: the order is chosen so that each merge can keep G1–G5 green. Section 15 now says so, and that R3's code verification checks it on the playbook's build while each task's QA enforces it. |
| 88 | L967+L970 | "so the global-unique fallback still answers and nothing breaks" | inconsistency · minor | What does a no-workspace `set_archived` on a shared type_id do on RK1's head, where L970 makes it resolve first and L509 says that today it archives every namesake? | RESOLVED | It raises the existing "Ambiguous" `ValueError` (database.py:7041-7057) instead of archiving every namesake, on purpose. RK1's text now names that one behaviour change, and RK1 gains a red-first test, `test_set_archived_without_workspace_on_shared_type_id_raises`. |
| 89 | L1025+L719 | "each section 10 criterion-1, -2, -3, -5 and -6 test is red on RK1's head" | reasoning · minor | On RK1's head a reparent, an archive and a soft delete already leave the type_id-keyed row in place. What fact does each of those criterion-2 tests (L719) assert that is false there, for a reason other than the missing `entity_uuid` column? | RESOLVED | None: those three hold today too. They are now marked keep-green regression guards (section 10), and RK2's red-first rule excludes them. The rename, re-attribution and shared-type_id tests stay red first, each for a behavioural reason. |
| 90 | L1027+L1046 | "since the files are disjoint" | inconsistency · minor | Are they? RK4's codemod edits the test calls 6.4 counts (L1046), and `churn_totals.py`, which made that count, walks `plugins/pd/ui`, including `ui/tests`, which RK3 edits (L1033). | RESOLVED | They weren't: `plugins/pd/ui` holds 3 production and 24 test calls the strict rule touches (`calvin/churn_ui_only.out`), and RK4's gates run `ui/tests`. RK3 now precedes RK4 and scopes those calls, so the order is RK1 → RK2 → RK3 → RK4 → RK5 → RK6. Swept: section 15's order, RK1's callers, RK3, RK4 and RK5. |
| 91 | L1053 | "It follows task 4A if possible" | vagueness · minor | What decides "if possible": who waits for task 4A, and for how long? | RESOLVED | Nobody waits. When RK5 is cut, the orchestrator checks develop for 4A. If 4A has landed, `display._rename` is gone; if not, it is declared, and 4A's own change later removes the entry and lowers the mark. RK5 and section 11 say so. |
| 92 | L1073 | "assigns all 369 inventory rows to exactly one task or to this list" | completeness · minor | Which task covers 1A's new test files at `4a6373f0` that read `workflow_phases` or assert a workflow row's `uuid` and `workspace_uuid` keys (`test_workflow_phase_writers.py`, `test_create_feature_lanes.py`, `test_backfill_scoped.py`, `test_projection_names_directory.py`), none of which has an inventory row? | RESOLVED | RK2 now owns the four files, listed in its rows. The coverage line records that they have no inventory row, since the inventory is at `77f06efb`. |
| 93 | L509+L581+L721 | "today" | ambiguity · minor | Which moment does "today" pin across the document (for example L509, L581, L721), and how does a reader of the copy in docs/plans tell when that was? | RESOLVED | Defined in the names list: "today" is the code at `4a6373f0` and the live registry at fingerprint `1790286038 4083712`, both as of 2026-09-26. |
| 94 | doc | (absent: the user-visible failure the re-key ends) | reasoning · minor | What happens to a pd user if the re-key does not happen this round: which action fails, and for whom? And what would that user see once section 1.2's bar is met? | RESOLVED | New section 1.3. Without the re-key, activating a feature whose type_id another workspace holds answers `feature_not_found` (feature_lifecycle.py:593-595); scoping that read alone seeds no row (:604-610), and later transitions update the other workspace's row (database.py:9783); `get_mini_spec` reads both namesakes' events. It hits terry_agent's namesakes today, and any future shared type_id. Once the bar is met: own rows, own event streams, one card per row. |
| 95 | doc | (absent: what would force another re-key) | reasoning · minor | What future change would force these two tables to be re-keyed again, and which of the seven criteria would catch it before it lands? | RESOLVED | Only a change of the key itself, the entity uuid. `enforce_immutable_uuid` forbids that in place; `rebuild_tool`'s re-mint is the one path that changes uuids, and it now maps both tables' `entity_uuid` through its old-to-new map (section 14). A forgotten mapping is caught: `wp_reject_unknown_entity` refuses the row, and `foreign_key_check`, now part of the rebuild's verification, reports the event. Retiring the table into events keeps the key (criterion 6). Added to 2.4. |

☑ 95 resolved · 0 open · 0 dismissed

## R3 revision record (2026-09-26)

- **What this is:** the plan's one revision after R3 (plan:313), applied by the design's author. It absorbs R3's premortem, build, rehearsal and blast findings as triaged in `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/dispositions.md` (114 findings in 79 rows). The calvin ledger section above is unchanged.
- **Scope:** every disposition row whose targets include this design (45 rows), and one row that names it only in its sweep (PM-LIVE-S3). Rows that target only the playbook are the playbook editor's; those this design now reflects are listed after the table.
- **Method:** as the calvin revision did, an edit script of exact-match replacements, each checked to match exactly once before it was applied, in `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/design-edit/`:
  - **anchor pass** (`stepA.py`): 107 code, 28 plan and 7 design rev 2.1 citations re-anchored on 84 lines of sections 1–15 (log: `stepA.log`);
  - **edits** (`edits1.py`, `edits2.py`, `edits3.py`, applied by `apply.py`): 127 replacements, 0 failed.
- **Revision-wide sweeps** (no single row): the status line, the evidence line's pointer to the calvin section, and the names of the playbook's tasks and the questions (:3, :29, :36-37).
- **The calvin ledger's item numbers** are the old section 9's: item 1 is now Q2, item 2 Q4, item 3 Q6, item 4 Q5, and item 5 Q3. Q1 and Q7 are new.
- **Blockers left for the user:** none (the triage's decision 5). Q1–Q4 are asked before R4 starts, Q5–Q7 at the sitting (section 9).

| Row | Verdict | Change made | Lines now |
|---|---|---|---|
| PM-CONS-W2 | accept | The header names Phase 1 as landed on develop `c1bbfae0`: 1A, 1B's W1 as executed, and 1C's scoped registration with its skip. Section 12 keeps 1B's W1 and 1C's registration (minus the skip). Section 14 adds R4-H's code-comment grep and its known hits. RK1 restates `check_workflow_drift`'s docstring and passes the workspace in MCPE-10's `resolve_ref` call. The coverage note names 1B's and 1C's test files, which have no inventory rows. | :5-14, :1016-1018, :1233-1240, :1334-1339, :1402-1403, :1460 |
| PM-CODE-W10 | accept-modified | The header states the anchor rule. Every row of `anchors-moved.txt` that names a line of sections 1–15 is applied, and the same line map re-derived the other moved citations there (107 code citations on the lines of the anchor pass). The calvin ledger's rows are left as calvin read them (the dispositions' rule). "today" now means develop `c1bbfae0`; measured figures keep their commit. Section 8's CLIs row cites `entity_status.py:107`, `:228-241` and `:244-257`; citations of code Phase 1 deleted say `4a6373f0`. | :5-14, :38, :156, :639, :650, :819, :830, :944, :999, :1005 |
| PM-CONS-W3 | already-handled | Already handled by 1C's skip. Section 1.3 says session start skips such a brainstorm file and RK2 removes the skip; Q5's Defer option says those files stay unregistered while the sitting waits. | :103-104, :874-914 |
| BUILD-S7 | accept | Section 4.2: the CHECK lists have the same allowed values as the live DDL, compared as sets by `test_fresh_and_staging_shapes_identical`; "verbatim" is gone. | :232 |
| BUILD-S2 | accept | Section 4.4 step 10: `migration_version` is the chain generation when the migration ran (8 if v2, else 26); staging-built and fresh files record 26, and a fresh file has a zero-count success row. | :369 |
| BUILD-S3 | accept | Section 4.4: step 5 runs only when the `workflow_phases` part is pending; step 9 checks only tables that exist on the file. | :350, :366 |
| BLAST-B1 | already-handled | Already handled by 4C's amended contract. Section 4.4 states the serialized, monotonic runner, the brick rate without it, 4C's race tests with migration 26 registered, the v2-chain test and "no re-run allowance". Section 10 criterion 5, and section 15's table, prerequisites and RK2, make RK2 wait for 4C or carry its contract. | :372-374, :937, :1277-1325, :1366-1368, :1374-1380 |
| PM-LIVE-W9 | accept | Section 5.1 Q-rows-kept: "pre" is the matched rows plus the re-attached rows, each keyed by its entity's current pair (a UNION ALL with the re-attach copy's WHERE); the live figure stays 529. | :439-456 |
| BUILD-W1 | accept | Section 5.1 Q-null-uuid: "pre" lists only NULL-uuid rows whose pair joins an entity; the live figure stays 8. | :461-465 |
| PM-LIVE-W8 | accept-modified | The label-decided predicate matches a workspace's legacy id or its uuid, and never `'__unknown__'`: the UPDATE and the expected-figures SQL (5.2), and the section 3.3 row. Section 5.2 adds why the lookup stays unique, why `'__unknown__'` never decides, and RK2's two test cases; section 3.2 names 1B's uuid label (dependencies.py:193). No live figure changes. | :187, :204, :507-519, :525-528, :557-560 |
| PM-CODE-B1 | accept | The uuid test covers the 15 pairs RK1 resolves (five red on base, ten keep-green, each recorded); `resolve_entity_uuid` and `search_by_type_id_prefix` have no uuid case (6.1, 6.3's list and rows); RK2 adds three cases. "Keep-green" is dropped from the test's name in sections 10 and 15. | :593-596, :641, :648-649, :936, :1354, :1374-1380 |
| PM-CODE-W1 | accept-modified | The refusal is `WorkspaceRequiredError`, re-raised by `get_entity`, `get_lineage` and every not-found handler (6.1). Section 8 states the propagation contract and today's swallowing callers, which RK4's flip converts with `test_refusal_reaches_the_caller[<site>]` (sections 10, 15). The codemod slices add `match=` to the 16 `pytest.raises` blocks. | :600-601, :649, :827, :936, :978, :1421-1423, :1427-1431, :1434 |
| PM-CODE-S4 | accept-modified | The pinned message names the parameter (`<parameter> '<value>' needs a workspace_uuid: …`), in 6.1 and in section 11's refusal check; tests still match `needs a workspace_uuid`. | :600-601, :978 |
| BLAST-S4 | accept | Section 6.3: `query_phase_events_bulk` refuses any element that is not a uuid, with `test_bulk_read_refuses_type_ids`. | :664, :1374-1380 |
| PM-CODE-W8 | accept | Section 6.5: a label-only call counts as unscoped (28 production calls at `5cc2ab75`), and the naming-rule fixtures add a workspace with no legacy id. Section 6.4 lists label-only calls among the count's misses and in the re-count. | :694-695, :702-710, :724-725, :1334-1339 |
| PM-CODE-W7 | accept | Section 7 states the UI's three cookie states, relabels the table (`'*'` cookie; the no-cookie board of a UI started in pedantic-drip's checkout), and makes a type_id URL answer 404 with no cookie or `'*'`, with two tests. Section 13.5's board figures are the `'*'` view; section 14's duplicate cost and RK3's tests follow. | :754-755, :759-761, :764, :773-776, :1190, :1256, :1406, :1418-1419 |
| PM-CONS-S1 | accept | Section 9's old item 1 is Q2, with its lasting costs (future callers, rebases, `workspace_unresolved`) and the scale measured at `ddc299a0`. | :719, :874-914 |
| PM-CONS-S2 | accept | Section 9 asks seven questions in two batches: Q1 (hold the sitting this round; pd off until then) before R4 starts, and the live yes (Q5) at the sitting. Each question says what it blocks; references to the old item 5 now say Q3. | :733, :851, :874-914, :1033, :1045 |
| PM-CONS-W6 | accept | Q6 replaces item 3: no change, archive pedantic-drip's five copies, or merge into terry_agent's; re-attribution is impossible under `UNIQUE(workspace_uuid, type_id)`. Section 5.3 states the five's state; section 14's rows say archiving or merging. | :576-577, :874-914, :1255, :1267-1269 |
| PM-CONS-W7 | accept | Q4 recommends deleting merge-entities (question 18 and Q4). Section 11: the entry is keyed by function plus a source sha256, and the high-water mark is at most 1 while `display._rename` exists (0 after 4A with merge-entities deleted, 1 if kept). Sections 14 and 15 follow the ruling. | :862, :874-914, :993, :996-998, :1008, :1243-1246, :1266, :1437-1440, :1456 |
| PM-LIVE-W5 | accept | `rebuild_tool`'s refusal message names the operator tool and never says to open the source (9 question 12, section 14). | :856, :1207 |
| PM-CONS-W8 | accept | Criterion 7's evidence names 1B's four W1 test files and 1C's test file (except the skip tests), whose assertions stay unchanged; the guard line stays as secondary evidence. Section 12 keeps 1B's W1 with them. | :939, :1016-1018 |
| PM-CODE-B2 | accept | Feature 129 needs two hand edits, the `HANDLERS` lambda (`test_cross_workspace_matrix.py:230-236`) and `:307`, owned by R4-F1 (criterion 7, section 12). | :939, :1025 |
| PM-CODE-W2 | accept | Section 11's rules resolve f-string, `%` and `.format` operands, count only unconditional workspace predicates, widen the type_id predicate, cover Python-built `/entities/` links and match parameter names by pattern; each R3 mutation becomes a self-test, and the limits are stated. Found while applying it: the patterns also match `query_phase_events_bulk.type_ids` and `refuse_deleted_or_cross_workspace_parent.child_ref` (message only), so the guard lists such parameters as exclusions with reasons. | :936, :958, :960-961, :969, :975, :977, :982-986, :1437-1440 |
| PM-CODE-W3 | accept | No allow-list change. Section 11's registry row notes that the migration keeps its SQL inside itself and tests inject failures through the SQL-free `_rekey_fault_point(stage)` seam. | :992 |
| PM-CONS-S3 | accept | `display._rename`'s entry: 4A cannot edit the guard while it exists only on `followups-phase-r`, so Phase R's rebase fix-up removes it once 4A lands, or 4A does if it lands after Phase R (section 11, RK5). | :994, :996-998, :1437-1440 |
| PM-CONS-W5 | accept-modified | Section 13.1: from R4's start every agent command runs with a temp HOME, each task's QA records the live file's version and fingerprint, a pd session in a Phase R clone would publish it (Q1), and the migration's live-path tripwire (with its test) backs the rule. Section 4.4 step 1 and criterion 5 carry the tripwire; section 13.3 applies through the operator tool; section 13.4 says the tripwire refuses a restored file. | :344-346, :874-914, :937, :1077, :1079, :1081-1088, :1122, :1139-1143, :1166, :1366-1368, :1374-1380 |
| PM-LIVE-W4 | accept | Section 13.2: a restart does not cure a session started on a pre-Phase-R branch; the cure is develop plus `sync-cache.sh`. R4-E's publish guard in `sync-cache.sh`, with its test, refuses an older schema build. | :1106-1110 |
| PM-LIVE-W6 | accept-modified | Section 13.3 step 6 makes a read-only post-apply copy; section 13.4 lists changed rows with the operator tool's `diff` subcommand. | :1152, :1169 |
| BUILD-W2 | accept | RK2 owns `TestMigration6`'s three row assertions whether or not 4B lands (section 14's Out list, section 15's rows and prerequisites). | :1249, :1366-1368, :1374-1380, :1387-1391, :1456 |
| PM-CONS-S4 | accept | Q7 asks the operator tool's fate; section 14 lists its deletion after the sitting under the one-off rule, if the user agrees. | :874-914, :1223-1224 |
| PM-CONS-W1 | accept | Section 12's plan changes are split: items 1–8 on develop now, items 9–10 in the sitting's commit, with a Done-when deferral clause. Section 14 adds the rows a recorded deferral adds. | :1048-1071, :1267-1269 |
| PM-CONS-S7 | accept | Every plan citation is re-anchored to develop `c1bbfae0` by `plan-anchor-map.txt` (28 citations), and design rev 2.1's by the same line map (7). Section 12's items cite the plan at `c1bbfae0`, and F1 steps 1–3 are confirmed unchanged. F3's order (migrate, verify, land, publish) is stated in section 12, section 13.3's governing note, Q5 and RK6. | :5-14, :17-20, :1048-1071, :1112-1114, :1119, :1446 |
| PM-LIVE-S5 | accept | F1 step 4's "Before" query adds `AND e.is_deleted = 0` (section 12, item 5); the figure stays 28. | :1048-1071 |
| PM-CODE-W11 | accept-modified | R4-C0 (shape-aware test helpers) is added with its dependencies (section 15's table, order and prerequisites), and RK2's files note it. The rejected part, a re-run allowance for the race test, becomes "no test gets a re-run allowance" (4.4, section 15). | :1274-1325, :1387-1391 |
| PM-CODE-W6 | accept | `set_archived` has taken a uuid since 1B, and `set_deleted` gains the same path (6.3's rows, open question 1, RK1's library and tests). | :654-655, :845, :1330, :1354 |
| BLAST-B3 | accept | Section 6.3's `feature_entity_id` row names the test_c11 rewrite and two deletions; RK1's files add both test files. | :650, :1343-1344, :1354 |
| PM-CODE-W9 | accept-modified | CLIs resolve read-only, as the UI does, never with a minting resolver; `frontmatter_sync_cli.py` is in scope; `backfill_headers` lists one workspace; no workspace means a warning, exit 0, nothing written; `cleanup_backlog` resolves before archiving. With 1C's skip gone, an unresolved orchestrator raises at the first registration and records it (section 8, RK1). | :830, :838, :1334-1339, :1343-1344, :1354 |
| BLAST-B2 | accept | RK2 removes 1C's skip: section 6.1 names the callers of `search_by_type_id_prefix` and the removal, its rewritten tests and the files; sections 6.3, 8, 12 and 15 follow. | :608-611, :648, :830, :1366-1368, :1387-1391, :1402-1403 |
| BLAST-W1 | accept | Section 6.3's `update_workflow_phase` row: the four `workspace_uuid mismatch` tests now expect the not-found error; RK2 lists them and `test_engine.py`. | :658, :1366-1368, :1374-1380, :1387-1391 |
| PM-CODE-S1 | already-handled | Already handled by 4C. Section 4.4 names 4C's race tests re-run with migration 26, the v2-chain case and the in-process peer case that stays. | :372-374 |
| PM-CODE-W4 | accept-modified | Figures re-measured at `ddc299a0` (2.3, 6.4, Q2, RK4); the entry-point table (sections 6.4, 8, 15); RK4 as four tasks with the sizing rule and census-based QA. Modified: the row's "about 1,200 direct" is written as the census's 1057 direct sites, the figure Q2 cites, with the static 1201 beside it. | :148, :702-710, :715-716, :719, :834-835, :874-914, :1274-1325, :1334-1339, :1421-1423, :1427-1431 |
| PM-CONS-W4 | accept-modified | Section 6.2's uuid greps re-run at every rebase; section 15 carries the per-rebase checklist, with its 4C item checking the runner and test isolation. | :633, :1277-1325 |
| PM-LIVE-W10 | accept-modified | Section 13.4: a remaining `-wal` is cleared with the operator tool's `checkpoint`, never by hand, and a killed apply's case is stated. | :1163-1164 |
| PM-CONS-S6 | accept-modified | Section 3.2 says `query_phase_events` returns the write-time label; criterion 2 parametrizes the re-attribution test over its three writers and adds the rebuild's re-mint; criterion 3 and section 11 add rule 6, the event-label check (RK5). | :189-190, :934-935, :982-986, :1437-1440 |
| PM-LIVE-S3 | accept | **Not applied.** No restatement in the design: its re-attach SELECT (5.1) already uses NOT EXISTS, and the dropped-rows SELECT with NOT IN is only in the playbook (2.2 step 6.2). | none |

**Rows with no design target that the design now reflects** (their text is the playbook's):

| Rows | Where |
|---|---|
| BLAST-W2 | R4-A's scope in section 15's table (:1283) and RK1's callers (:1337) |
| PM-CONS-S8 | section 12, item 2, the rebase rule (:1053) |
| PM-CODE-S3 | section 12, item 4 (:1055), and section 15's prerequisites, R4-F3 (:1313) |
| BLAST-S1 | R4-C's gate expectation in section 15's table (:1286) |
| BUILD-W3, BUILD-S4, BUILD-S6, PM-CODE-W5 | R4-C's scope in section 15's table (:1286) |
| REH-W1, PM-LIVE-W1, PM-LIVE-S2, REH-S1, PM-LIVE-W2, BUILD-S8, REH-W4, REH-S9, REH-S3 | R4-E's scope in section 15's table (:1288) |
| BLAST-S2 | R4-F1's scope in section 15's table (:1289) |

**Playbook only, nothing here restates them:** PM-CODE-S2, BUILD-S5, PM-LIVE-S7, PM-LIVE-W3, PM-LIVE-W7, PM-CONS-W9, PM-LIVE-S1, REH-S8, PM-LIVE-S4, REH-S2, PM-LIVE-S6, REH-S5, REH-S6, REH-S7, REH-S10.

**Checker gaps (applied after the completeness check)**

- **Source:** `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/check-report.md`: 0 blockers, 3 warnings (W1–W3) and 6 suggestions (S1–S6).
- **Method:** 13 exact-match replacements here (22 in the playbook), each checked to match exactly once (`/private/tmp/claude-501/-Users-terry-projects-pedantic-drip/27cf8870-ad10-4a78-9c82-03da65e2304a/scratchpad/r3-gaps/apply_gap_edits.py`). No edit changed a line count, so the line numbers above still hold; the one range that moved inside 13.3 is updated in PM-CONS-W5's row.
- **Left as written:** the calvin ledger's pointers to 13.3's old step numbers (rows 61, 70 and 80), since this revision leaves the ledger unchanged.

| Gap | Change made | Lines now |
|---|---|---|
| W1 | None here. The playbook's R4-A now cites this design's `c1bbfae0` lines for 6.3 and 8, and its header takes this design's anchor rule. | none |
| W2 | 13.3's steps now run in the order its note gives. Step 3 is "Apply": the fingerprint check, then the apply, from a scratch clone at the commit develop will fast-forward to. A new step 5, "Land", holds the fast-forward and records the commit develop pointed at; Record and Publish are steps 6 and 7. Pointers renumbered: section 12, item 10 (step 6); 13.4 (steps 5 and 6); PM-LIVE-W6's row (step 6); PM-CONS-W5's range for the apply block (:1139-1143). | :1137-1153; :1069, :1166, :1169, :1608, :1610 |
| W3 | The 404 test runs on the shared-type_id fixture plus a type_id one workspace holds, whose red on the base is a 200, as the playbook's R4-D has it. | :776 |
| S1 | None here (the playbook's question pointers). | none |
| S2 | R4-F4's row cites "the playbook's R4-F4 changes (1.8.4)", not the old "R4-F changes 1–6". | :1292 |
| S3 | R4-F3's row adds 1B's `test_update_entity_archived.py` (`plugins/pd/mcp/`). | :1291 |
| S4 | The per-rebase checklist greps `.get('uuid')` beside `row['type_id']`, as the playbook's 1.12 does. Swept: 6.2's pointer to that checklist says the same. | :1321; :633 |
| S5 | The code-comment grep's hits at `c1bbfae0` are listed in full, each confirmed by re-running the grep there. | :1240 |
| S6 | None here (the playbook's precondition 11). | none |

## Now

Legacy item, adopted by pd-adopt on 2026-10-21.

## Log
