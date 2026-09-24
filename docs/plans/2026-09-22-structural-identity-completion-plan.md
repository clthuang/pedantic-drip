# Structural Identity — Completion Plan

**Parent plan:** [2026-09-20-display-id-ownership-implementation.md](./2026-09-20-display-id-ownership-implementation.md) — the Contract/Interface/Verify text for **C1–C23** lives there and is **not restated here**. This document sequences what is left, records the corrections found while scoping it, and closes the one question the parent plan left open.
**Design:** [2026-09-20-display-id-ownership-design.md](./2026-09-20-display-id-ownership-design.md) (rev 3)
**RCA:** [../rca/20260920-display-id-ownership.md](../rca/20260920-display-id-ownership.md)
**Related, shipped:** [2026-09-22-soft-delete-design-and-plan.md](./2026-09-22-soft-delete-design-and-plan.md) (#081, `76c4a4cc`)

**Before executing any task below, run `calvin` on this document** (per `~/.claude/CLAUDE.md`). It Wave 2 carries a ledger as of 2026-09-23 (*Calvin ledger*, end of the Wave 2 section); the rest of the document still carries none.

---

## Ground truth, measured 2026-09-22

Every number below was read from the live registry or the tree today. Re-derive before execution — the registry is shared with 23 other workspaces that keep writing to it.

| Fact | Value |
|---|---|
| `schema_version` | 6 (v2 generation) |
| Entities | 579 |
| `is_legacy` | 180 |
| `is_archived` | 170 |
| `is_deleted` | 0 |
| Entities with **no** `entity_display` row | **180 — exactly the `is_legacy` set** |
| Legacy rows, by filter | **180** raw · **148** `AND NOT is_archived` · **16** `AND` live status · **11** with both |
| Children whose `parent_uuid` points at a legacy row | **79** (16 under `P004-entity-db-redesign`, 29 under cast-below's `P001`, 15 under terry_agent's pair) |
| Identity-inference sites detected | **28 declared** (7 sanctioned, 21 to remove) — `promote_entity`'s `type_id.split` left with it in `2d654e1a` |
| Python suite | 3902 passed / 3 skipped — **now 3975 / 3** at `38935d59`, after C4/C23/C1/C2, `2d654e1a` (six promotion tests removed) and C17a (five tests added in this scope) |
| `./validate.sh` | 0 errors / 0 warnings |
| Hook integration tests | 66/66 passed, 1 skipped |
| `register_entity`/`upsert_entity`/`register_entities_batch`/`_register_entity_no_display` call sites | **13 external production · 3 internal · 1,152 test** across 48 files at `38935d59` (a 3-name census undercounts by 25; `scripts/census_register_sites.py`, step 0) |
| Tests that fail once identity is mandatory (`STRICT_ID_FORMAT=1`) | **751** (707 failed + 44 errors) across 26 files — **693** `EntityIdFormatError`, 14 assertion-shaped (13 downstream of it, **1 a second class**) |
| Live `schema_version` vs build | file **6** · build `V2_SCHEMA_VERSION` **7** — migration 7 is already in the live plugin and applies at the next pd MCP start; rehearsed on a copy 2026-09-23 (see the gate, step 4). **Corrected 2026-09-24:** pd is disabled, so no MCP server starts; applied by hand, gate step 7 |
| Brainstorms | 100 · **97 carry display rows** (all non-legacy) · 3 without, all `is_legacy=1` |
| Workspaces with no `project_id_legacy` | **10 of 24** — 7 are deleted directories (4 stranded entities, a dead counter at 88); **3 are live worktrees of project_illium**, which `project_id` resolves to the **parent's** workspace (measured 2026-09-23). **C17a (`833095a9`) retired the 3 worktree rows: 21 workspaces remain** |
| Feature directories the registry has never seen | **152** — project_illium 78, fractorg 57, terry_agent 16, pedantic-drip 1 (read-only scan, 2026-09-23) |
| Feature counters behind their disk | project_illium 57 vs dirs to 114, terry_agent 36 vs 50 — **raised to 115 and 51 on 2026-09-23** (snapshot `entities.db.pre-counterfix-20260923`); the 3 illium worktrees' own buckets went with their rows (C17a) |

**Shipped since the parent plan was written:** Release A (`96b2f88a`), C20a (`12f1b571`), B1 (`b7bf5040`), B3 (`b7bf5040`), B4 (`6f971b28`), B5 (`6faf7222`), B6's marker half (`6f971b28`), three orthogonal flags — `is_legacy` (`d42689b1`), `is_archived` (`bb0fb55e`), `is_deleted` (`76c4a4cc`).

---

## Decisions — locked 2026-09-22

**1. `docs/backlog.md` filters on status and scope, not on legacy-ness.** `NOT is_archived AND status IN ('open','active')`, scoped to the invoking workspace. 170 rows → **25**.

This **corrects parent B7's Contract**, which says marked entities do not appear and would therefore hide 6 open items (`00059`, `00060`, `00177`, `00180`, `00183`, `00190`) that are unfinished work whose ids merely predate the structural model. "Is this row old?" and "is this work open?" are different facts; a backlog view wants the second. Filtering on `is_legacy` would be the same category error this effort exists to remove — inferring a semantic fact from a structural accident. B7 rewrites the Contract rather than implementing it.

**2. C22 recreates the 11 unarchived live rows, collapsing to 10.** 6 backlog items + 4 projects (`P001` after `P001-openclaw-gap-analysis` collapses in, `P002`, `P003`, `P004-entity-db-redesign`).

The 5 archived live-status rows stay archived — recreating them would contradict the flag, and after decision 1 none appear in any projection. Two of them hold children, which decision 3 handles. Two are in terry_agent, which C22 cannot reach.

**3. Re-parenting gets a real API: `reparent_entity`.** `EntityDatabase.reparent_entity(type_id, new_parent_uuid)` — a uuid-to-uuid write with no text in it, emitting an event like other mutations, with the existing self-reference triggers still applying.

C22 calls it for the **25** children of recreated projects (`P002` 5, `P003` 4, `P004-entity-db-redesign` 16 — all 25 `completed`). This keeps C22's "no bespoke insert" rule intact: that rule exists to stop C22 hand-crafting *identity*, and moving a foreign key is a different act. `update_entity` does not accept `parent_uuid` today, so without this there is no legal path.

**Residue, stated rather than implied.** 10 children stay on archived parents in this repo (including the 1 child of `P003-entity-system-redesign`). 44 more hang off parents in cast-below (29) and terry_agent (15); C22 runs in the current project's context and cannot reach them. Each of those repos needs its own cutover, or keeps legacy lineage permanently.

**4. Wave 2 is a hard cutover with a manual stop.** Single operator, single machine, all sessions under one person's control — so the mixed-version window is closed by stopping everything, not by code.

C23 is therefore **not** load-bearing for this cutover and does not need splitting. It ships in Wave 2 as written and protects the *next* one. What protects *this* one is the gate below.

**5. `promote_entity` is deleted** (2026-09-23, `2d654e1a`). Feature 109 built it to replace the backlog→feature path and never switched a caller over. Promotion registers a new feature entity with the source as its parent, and every status/phase change goes through `append_phase_event()`, so nothing depended on it. It was the only runtime writer of `entities.kind` and held C12's `type_id.split`; both went with it.

**6. A git worktree uses its repository's workspace** (2026-09-23). One number sequence per repository, so a feature minted on a worktree branch cannot reuse main's numbers when the branch merges. The repository is identified by `git rev-parse --git-common-dir`, not the root commit, which separate clones also share. terry_agent's working tree keeps its git directory in a bare repository, so "the repository" does not always have a main checkout to map to. Implementation is **C17a**, under Wave 4.

---

## Decided — the display-row question

The parent plan's Risks section proposed backfilling `entity_display` rows for the 180 legacy entities, so the census would protect their numbers structurally instead of relying on one counter per bucket.

**Decision: do not backfill.** The evidence, measured today:

- 176 of the 180 legacy ids yield a sequence via `parse_legacy_seq`. Four do not, correctly: three brainstorms carry timestamp identity, and `feature:unnamed-b43fd0f1` has no sequence at all.
- **25 of those 176 collide** with an existing live display row at the same `(kind, workspace_uuid, seq)`. They are the two-generation backlog overlap — legacy `00063` and live `063-watch-code-quality-reviewer-fix-rate` are different entities that both claim 63.
- **4 more collide inside the legacy set itself** — the duplicate project pairs.
- `entity_display` has `uuid` as its only primary key and a **non-unique** index on `seq` (`database.py` `CREATE INDEX idx_entity_display_seq`). A backfill would therefore **not** raise. It would silently install 29 ambiguous `(kind, workspace, seq)` pairs and make every future seq→entity lookup non-deterministic.

**What replaces it.** State the fact that is already exactly true, and enforce it:

> **Every entity has an `entity_display` row unless `is_legacy = 1`.**

180 legacy rows, 180 display-less rows, the same 180 — set equality, not just matching counts. This is checkable today, needs no data migration, and gives **C3** a predicate that is a stated column rather than an inference — which is the through-line of this whole effort. It is added as **B8** below.

**The invariant is only sound if `is_legacy` is immutable.** As shipped the column has no trigger, no write-path guard and no doctor check, so "every entity has a display row unless `is_legacy = 1`" can be satisfied by relabelling the offending row instead of fixing it — and C3 would then permit exactly the bucket it exists to refuse. B8 therefore carries an `enforce_immutable_is_legacy` trigger, on the same pattern as the table's existing `enforce_immutable_uuid` / `_created_at` / `_workspace_uuid`. Without part (b) of B8, this decision is worse than the backfill it replaces.

---

## Corrections to the parent plan

Found while scoping. Each changes what a task must do, so each is listed before the work rather than inside it.

1. **B2 is unstarted, not shipped.** `_INFERENCE_SCAN_ROOTS` (`test_audit_writes.py:499`) is still `[hooks/lib, mcp]`. `_card.html:4` and `:10` both run `item.type_id.split(':')` and remain invisible to the audit.

2. **B6's marker is a column, and only a column.** The parent plan specifies `entity_tags` as the carrier and argues at length against metadata. Shipped reality is `entities.is_legacy` alone — the `legacy-archived-2026-09` tag **does not exist in the registry**. Its removal was deliberate and is recorded in [entity-archive-manifest.md](../entity-archive-manifest.md): *"The earlier `legacy-archived-2026-09` tag was removed once the column existed: two homes for one fact is the defect this effort removes."* `entity_tags` holds only `workspace-retired-2026-09` (9 rows), which says something different.

   **The live consequence is parent C3's gate.** C3 specifies its predicate as "B6's tag" and its live-precondition gate as *"assert `select_legacy_entities(live_conn)` returns 0 against the live DB"*. Measured:

   ```
   select_legacy_entities(conn)                                    -> 180
   select_legacy_entities(conn, marker_tag='legacy-archived-2026-09') -> 180
   ```

   `select_legacy_entities` keys on `is_legacy = 1` (`clean_break.py:115`) and returns 180 unconditionally, forever. It is a **selector of the legacy set**, not a worklist that drains — the "returns 0 after" framing only ever made sense under the tag model. C3's gate as written can never go green. **B8 is its replacement.**

3. **Neither plan has ever enumerated C22's pair-collapse scope correctly.** There are **four** duplicate project pairs. The parent names three; my first revision named a different three. Union 4, intersection 2.

   | Pair | Workspace | Children | Survivor (later `created_at`) |
   |---|---|---|---|
   | `P001` / `P001-openclaw-gap-analysis` | pedantic-drip | 0 + 0 | `P001` |
   | `P002` / `P002-memory-flywheel` | pedantic-drip | 5 + 0 | `P002` |
   | `P003` / `P003-entity-system-redesign` | pedantic-drip | 4 + 1 | `P003` |
   | `P001` / `P001-agent-orchestrator` | **terry_agent** | **12 + 3** | `P001` |

   The parent's `5+0, 4+1, 12+3` are all **correct** — `12+3` is terry_agent's pair, which my first revision wrongly dismissed as describing nothing. What the parent omits is pedantic-drip's own `P001` / `P001-openclaw-gap-analysis`. `P004-entity-db-redesign` is unpaired (16 children); so is cast-below's `P001` (29 children).

   An executor trusting either list under-collapses. Re-derive the four groups from `(kind, workspace_uuid, parse_legacy_seq(...))` at execution time rather than reading any literal here.

4. **C7's call-site list is missing two sites.** Beyond the parent plan's enumeration: `reconciliation_orchestrator/entity_status.py:190` (an `upsert_entity` that Release A introduced) and `plugins/pd/scripts/parse_backlog_md.py:254` (outside both scan roots, so the lint will never name it — note the path is under `plugins/pd/`, not repo-root `scripts/`, which exists and holds different files). `database.py:10432` has drifted to `:10727`.

5. **Release C's ordering hazards are encoded; its `Depends` graph is not wrong.** No correction needed — noted so the next reader does not re-verify it.

6. **The parent plan miscites `TERMINAL_STATUSES`, twice over.** It reads *"production's own `TERMINAL_STATUSES = {promoted, abandoned, archived}` (`entity_status.py:10`)"*. Actual: `entity_status.py:21`, and the set is `{"promoted", "abandoned"}` — `archived` was removed when archival became a flag. B5's cross-workspace blocker was cleared using `clean_break.py:81`'s `is_live` predicate; under the authority B5 actually cites, the clearance does not follow. The blocker's *conclusion* still holds on the evidence recorded in B5, but its stated basis does not.

7. **Neither plan ever sized Wave 2's test surface.** The parent plan's *"roughly 15 production sites"* is accurate (16 measured). What no revision counted is **1,153 test call sites across 49 files** (1,151 across 48 once `2d654e1a` deleted a test file, 1,152 at `38935d59`) (a three-name census undercounts by 25 — `_register_entity_no_display` is a fourth), or the **751 tests** that fail the moment structured identity becomes mandatory, which itself cannot see those 25. Wave 2's cost is in the suite, not in production. Re-planned in full below.

8. **C5 removes two parameters too many.** `project_id` and `parent_type_id` appear nowhere in `_KNOWN_INFERENCE_SITES` and involve no schema change, so they split out as **C5b**. The justification is design risk, not edit count — 7 of 13 external production sites pass `project_id` with no `workspace_uuid`, and in git worktrees `project_id` resolves to the parent repository's workspace (decision 6, C17a). (Rev 1 of Wave 2 argued from an edit count of 1,072; that figure double-counted two overlapping sets — the union is 973, and 960 of those ride along on lines C5 already rewrites — three-name counts; over all four names it is 996 and 983, the same 98.7%. Withdrawn.) See Wave 2 / D1.

9. **B8's invariant goes false the moment brainstorm takes the `display_id` path.** "Every entity has an `entity_display` row unless `is_legacy = 1`" has no exemption for kinds that have no sequence identity, so the first brainstorm registered after Wave 2 turns `check_display_row_invariant` red. The invariant is restated — and its eight restatements swept, including the check's own SQL, its operator-facing message, and parent C3's predicate — inside the C5 commit. See Wave 2 / D3.

10. **Correction 9 must carry into C18, not only the doctor check.** Parent `## C18`'s Verify states *"every entity `run_backfill` creates has an `entity_display` row and an `entity_id` equal to `render_display_id(kind, seq, slug)`"*. `run_backfill` creates brainstorms (`backfill.py:191` → `_register_brainstorm` at `:837`), which post-D3 have no display row, and `render_display_id` **raises** for brainstorm (`id_generator.py:80`). C18's Verify gains the same `NON_SEQUENCE_KINDS` exemption: such entities carry a verbatim `display_id` and no display row. Half-sweeping this is the exact class the Corrections section exists to close.

---

# Part 1 — Finish Release B — **COMPLETE 2026-09-22**

Four tasks, none of which depends on the cutover. **B2, B3b and B8 are shippable as soon as their scope questions are answered; B7 is blocked on a decision** (which rows `backlog.md` should show) and on carrying its five downstream consumers.

## B2 — Widen the audit to UI templates

**Contract.** The identity-inference audit covers Jinja templates. A template that decomposes `type_id` is reported exactly as a Python site is.

**Interface.** `_INFERENCE_SCAN_ROOTS` (`test_audit_writes.py:499`) gains `plugins/pd/ui/templates`. `identity_inference.scan_roots` grows a Jinja expression extractor — parse `{{ … }}` and `{% set … %}` bodies, feed each to the existing `iter_inference_sites`. Both new sites join `_KNOWN_INFERENCE_SITES` with owner `C8 kind from entities.kind`.

**SHIPPED 2026-09-22.** Both sites reported at exactly lines 4 and 10.

**Verify.** `_card.html:4` and `_card.html:10` are both reported, with idiom `split`. `test_identity_inference_inventory_is_exact` (`test_audit_writes.py:597`) is the exact-set lint — detected == declared — and enforces no count; it goes from 28 to 30 declared sites and still fails on any addition **and** any undeclared removal.

**Two decisions B2 must make explicitly, not discover.**

1. **The `<= 28` ceiling.** ~~`test_inventory_shrinks_to_zero_eventually` hard-asserts `<= 28`; B2 fails at 29.~~ **Done.** Replaced with `_INVENTORY_HIGH_WATER = 30` carrying a table of why it moved (28 initial → 30 for B2's scan root), and a docstring distinguishing "we found more" from "we wrote more". The old bare ceiling reported a detection widening as a regression.
2. **Who removes the two template sites.** They are labelled `C8 kind from entities.kind`, but parent C8's site list is Python-only (`router.py:358,421`; `frontmatter_sync.py:109`; `workflow_state_server.py:1113,1395`) and Wave 4 widens C8 only by a fixture. Removing a Jinja `type_id.split(':')` means the **view** passes `kind` into template context — a different change in a different layer. Either widen C8's scope to name the template and its view, or create a UI task. Left as-is, parent C21's lint-green contract cannot be met.

**Non-vacuity gate.** Assert the reported line numbers are 4 and 10. A root that scans the directory but extracts nothing reports zero sites and passes an "audit ran" assertion.

**Depends.** Nothing.

## B3b — Give the three unowned sites owners

**Contract.** Every entry in `_KNOWN_INFERENCE_SITES` names a task that will remove it or a policy that sanctions it. No entry says `UNOWNED`.

**Interface.** Three relabels, one of which is a real finding:

| Site | New owner | Why |
|---|---|---|
| `entity_registry/database.py:927` | `migration internal - sanctioned` | It sits inside `_schema_expansion_v6` (v1 migration 6), seeding `next_seq_{type}` from historical `entity_id` text at migration time. Same class as `:2755`, `:4198`, `:4261`. Relabel; do not fix. |
| `workflow_engine/feature_lifecycle.py:97` | `C11 artifact path` | `_validate_feature_type_id` splits `type_id` on `:` and builds `{artifacts_root}/features/{slug}`. The path belongs in `entities.artifact_path`. |
| `workflow_engine/reconciliation.py:787` | `C8 kind from entities.kind` | `row["type_id"].startswith("feature:")` filters `list_workflow_phases` output by kind. |

**Carry into C11.** `_validate_feature_type_id` is a **trust boundary** — it rejects `\0` and does a realpath containment check against `artifacts_root`. Sourcing the path from `entities.artifact_path` moves where the string comes from; it must not remove the containment check. A stored `artifact_path` is not more trustworthy than a parsed slug.

**Carry into C8.** `list_workflow_phases` already returns `e.kind AS entity_type`, so the swap looks free. It is not: the query **LEFT JOINs** entities, and orphan rows (`e.uuid IS NULL` — retained deliberately for anomaly visibility) get `entity_type = None`. Today's `startswith("feature:")` reads the `workflow_phases` row's own `type_id` and therefore **still classifies orphans as features**. The C8 fixture must contain an orphan `workflow_phases` row whose `type_id` starts `feature:` and assert which way the reconciler's `db_only` set goes. Decide it deliberately; do not let the join change it silently.

**Verify.** No inventory *entry* carries owner `UNOWNED` (grep the tuple lines, not the file — the rationale comment above the inventory names the token deliberately). Sanctioned rises 6 → 7; removable falls 22 → 21. Measured after: 28 entries, 7 sanctioned, 21 to remove, 0 unowned.

**SHIPPED 2026-09-22.**

**Depends.** Nothing.

## B7 — Render real identity, scope the read — **SHIPPED 2026-09-22**

The parent plan's B7 has two halves. The archived filter shipped with `is_archived` (`bb0fb55e`) — `_project_backlog_md` now filters on the flag, not on `status == "archived"`. What remains is the renderer and the scope.

**Contract.** `docs/backlog.md` displays each item's actual `entity_id` and contains only items belonging to the workspace it is written for.

**Interface.**
- `workflow_state_server.py:743` and `:789` both build `f"{d['seq']:05d}"`. Emit the row's real `entity_id` instead. Zero-padding a bare seq is what manufactures the collision.
- `workflow_state_server.py:633` calls `db.list_entities(entity_type="backlog")` with no workspace. Pass the invoking workspace. The docstring's claim that "cross-project backlog is a single file" is what licensed the unscoped read; the file lives in one repo and should show one repo's backlog.

**Why this is the highest-value single fix left.** `docs/backlog.md` renders 170 rows:

```
140  render their own entity_id exactly   ← legacy rows round-trip: 00096 -> seq 96 -> "00096"
 30  render something else (17.6%)
      |- 25 collide with a different, archived entity
      |-  5 match no entity at all
```

The canonical case: live `063-watch-code-quality-reviewer-fix-rate` renders as `00063`, which is a different archived legacy row. Separately the unscoped read pulls in **4** live rows from outside pedantic-drip — `003-json-ast-aware-check-in` (terry_agent) and `005/006/007` (illium-strategy-optimization), which are the first three visible ids in the file.

*(An earlier revision of this document said "83% of the rendered table names the wrong entity." That put a 25/30 ratio over the wrong denominator. The correct figure is 25/170 = 14.7%.)*

**B7 corrects parent B7's Contract (decision 1).** The parent says marked entities do not appear, and the marker is now `is_legacy` — but 140 of the 170 rendered rows are legacy (117 `dropped`, 17 `promoted`, **6 `open`**), and the 6 open ones are live work. The filter becomes `NOT is_archived AND status IN ('open','active')`, scoped to the workspace:

```
170  today
-117  dropped
 -17  promoted
  -4  foreign workspace
----
 25  open/active, pedantic-drip
```

Legacy-ness plays no part in the projection. All 6 open legacy items stay visible until C22 recreates them.

**B7 breaks five consumers, none of which the parent plan names.** The rendered id column is parsed back by:

| Consumer | Pattern | Breakage |
|---|---|---|
| `plugins/pd/scripts/cleanup_backlog.py:131` | `^- (?:~~)?\*\*#(?P<id>\d{5})\*\*` | matches zero items, returns 0, never re-projects |
| `plugins/pd/scripts/cleanup_backlog.py:39` | `^- (~~)?\*\*#\d+\*\*` | also fails — `#063-watch…**` has no `**` after the digits |
| `plugins/pd/scripts/parse_backlog_md.py:38,41` | `\d{5}` table-row and bullet forms | same |
| `plugins/pd/scripts/test_debt_report.py:26` | `(\d+)\*\*` | breaks by the same `**`-placement mechanism |
| `plugins/pd/scripts/compare_backlog_projection.py` | whole-text diff | diverges wholesale |
| `plugins/pd/hooks/lib/entity_registry/backfill.py:27,28` | `\d{5}` markers **inside feature docs** | `*Source: Backlog #00063*` stops corresponding to anything rendered |

`cleanup_backlog.py` is the **only** re-projection path — `data_file_guards/backlog_decision.py:22` denies every other write to `docs/backlog.md`. So after B7, B7's own Verify ("regenerate `docs/backlog.md` and assert per row") has no available regeneration path, and the file's only maintenance tool is silently dead. **B7 must carry those consumers in the same change.**

`backfill.py:27-28` is the one that outlives B7 by the longest: people copy the id they see in `backlog.md` into PRDs as `*Source: Backlog #00063*`. After B7 they would write `#063-watch-…`, the marker stops matching, and the backlog→feature link is silently lost for every document written afterward. That is a format contract with humans in the loop, not just with parsers.

**Worst case if the order is wrong:** `parse_backlog_md.py:254` registers each unmatched row into `project_id="__unknown__"` with `status="open"` and catches failures at `:265` as a stderr warning — so running it after B7 and before its parser is updated can mint up to 170 duplicate rows, each soft-delete-only and each carrying permanent events.

**Verify.** Regenerate `docs/backlog.md` and assert, per row, that the rendered id **equals** the entity's stored `entity_id` — not merely that the file changed. Assert the 4 foreign rows are gone. Add a fixture where a live row's `seq` matches an archived row's numeric `entity_id` and assert the live row renders its own id. Then run `cleanup_backlog.py --apply` and assert it still matches every item it matched before.

**Non-vacuity gate.** An assertion that "no two rendered ids are equal" passes today: the 25 collisions are with rows the projection already excludes. Compare each rendered id to *its own* entity's `entity_id`. And a `cleanup_backlog` run that matches **zero** items also reports no error — assert the match count, not the exit code.

**Depends.** Nothing. (The parent plan's `Depends: B6` was satisfied when the marker shipped.)

## B8 — The display-row invariant — **SHIPPED 2026-09-22**

**Contract.** The registry states and enforces: every entity has an `entity_display` row unless `is_legacy = 1`. Green today; red the first time a writer creates a non-legacy entity without a display row. `is_legacy` becomes immutable, so the invariant cannot be satisfied by relabelling.

**Interface — three parts, all required.**

**(a) The check.** New check in `plugins/pd/hooks/lib/doctor/`, registered in `CHECK_ORDER` and added to `_ENTITY_DB_CHECKS` (it reads the DB — cf. `__init__.py:44-47`, where `check_v2_cutover_window`'s exclusion is documented *because* it reads a file instead).

```sql
SELECT e.uuid, e.kind, e.entity_id
FROM entities e LEFT JOIN entity_display d ON d.uuid = e.uuid
WHERE d.uuid IS NULL AND NOT COALESCE(e.is_legacy, 0);
```

**(b) An immutability trigger on `is_legacy`.** Without this the invariant has an escape hatch, and B8 teaches it: the cheapest way to green a red check during the pre-C6 window is to set `is_legacy = 1` on the new display-less rows — which then makes **C3 permit exactly the bucket it exists to refuse**. `clean_break.py:92-97` already draws the distinction the hatch erases: an `is_legacy = 0` row with no display row *"is a bug, not history."*

Measured: `is_legacy INTEGER NOT NULL DEFAULT 0`, no trigger, no guard, no doctor check; the sole writer in source is the one-time migration `UPDATE` at `database.py:6276`. The same `entities` table already carries `enforce_immutable_uuid`, `enforce_immutable_created_at` and `enforce_immutable_workspace_uuid` — `is_legacy` was simply left out of an established pattern. Add `enforce_immutable_is_legacy` on that pattern. Since #081 removed hard delete, no other remediation for a display-less row exists, which is precisely why the hatch would get used.

**(c) The doctor test corpus.** B8 cannot go green without this, and the doc that omits it is claiming a gate it does not have:

| Surface | Today | B8 needs |
|---|---|---|
| `test_checks.py:1051` `EXPECTED_CHECK_COUNT = 10` | asserted at 11+ call sites | 11 |
| `test_doctor.py:15-25` | ordered content-equality pin on all 10 `CHECK_ORDER` names | new name, in position |
| `test_checks.py::_make_db` | *"minimal entity DB with legacy schema"* — no `entity_display`, no `is_legacy` | a fixture B8's SQL can actually execute against |
| `README.md:36`, `plugins/pd/README.md:46` | both say `/pd:doctor` runs **10** checks | 11 |

**Exit code — the doc's earlier claim was wrong.** An earlier revision said B8 would "exit non-zero, unlike `check_status_write_path` which is warning-only". The first half is unachievable and the contrast is false: `doctor/__main__.py:8` states *"Exit code is always 0"* and `main()` contains no `sys.exit` — **no** doctor check affects the exit code. Giving doctor a failing exit code silently re-contracts all 10 existing checks and is out of scope here. B8's enforcing gate is therefore **pytest**, on the pattern the repo already uses for `check_status_write_path` (whose authoritative gate is `test_event_sourced_state.py`, not the doctor run).

**Why it must land before C3.** C3's guard refuses allocation when a bucket holds non-legacy entities lacking display rows. Between now and C6, `init_project_state` still passes `_strict_id_format=False` (`feature_lifecycle.py:326`) and `register_entity` writes the display row only `if strict:` (`database.py:7637`) — so **every project created in any of the 24 workspaces adds a fresh violation**. C3 then refuses that bucket forever. B8 turns a silent accumulation into a failing check the moment it starts. It also replaces parent C3's live-precondition gate, which is unsatisfiable as written (see Correction 2).

**Verify.** Green on the live registry (0 rows — confirmed today). Insert a non-legacy entity with no display row into a fixture; assert the check fails and names that uuid. Then assert that `UPDATE entities SET is_legacy = 1` on that row **raises**, rather than turning the check green — that assertion is the whole point of part (b).

**Non-vacuity gate.** A `try/except` around a missing `entity_display` table makes the hermetic 0/0 test pass on the legacy-schema fixture while the check never runs. The fixture must contain the table, and one test must observe the check in its **failing** state.

**Depends.** Nothing. Ship early; it measures the drift the rest of the plan has to live with.

---

# Part 2 — Release C, the cutover

Task definitions are in the parent plan. This section only sequences them and marks where the corrections above apply. **Shipped from Part 2 as of 2026-09-22:** C4 (`235f7d0f`), C23 (`c621f3e5`), C1 and C2 (`e9f5774f`). Wave 2's remaining core — C5, C6, C7 — is re-planned below and unstarted.

## Wave 1 — version guard for the next cutover

**C23.** No dependencies; ships first. An old MCP server holding the shared plugin cannot write to a post-cutover file. Without it, `_migrate_v2` loops zero times on a file newer than the build (`database.py:10876`) and writes anyway — the only `V2_SCHEMA_VERSION` reference on the write path is the import-time `assert max(V2_MIGRATIONS) == _V2_SCHEMA_VERSION` at `:6496`, which compares the build to itself.

**C23 cannot protect its own cutover.** The assertion lives in `EntityDatabase.__init__` of the build that also performs the version bump, so it is absent from every process that predates it. That is not a defect to fix here — it is inherent to a read-side guard shipping alongside the write it guards.

**This cutover is protected operationally instead (decision 4):** a hard stop-the-world before Wave 2, cued to the operator, verified with `ps` and `lsof`. See the gate at the top of Wave 2. C23 **shipped 2026-09-22 (`c621f3e5`)** ahead of Wave 2 and guards the *next* version bump, when every running process will already carry it.

## Wave 2 — the locked core — **RE-PLANNED 2026-09-22, rev 2 after review**

**C4 SHIPPED 2026-09-22** — `render_display_id` is the sole composer; the `P` prefix is gone; `_PROJECT_DISPLAY_RE` deleted.

Rev 1 of this section stopped at the pre-flight gate and re-planned the wave around a measured test surface. Review found three blockers in rev 1 and two wrong claims of its own; rev 2 records the corrected measurement, drops the red-window build order for one that is never red, and states the errors rather than quietly fixing them. Line numbers are as of `2d654e1a`, which shifted `database.py` and `entity_server.py`.

**What Wave 2 solves** (calvin L10). Production already registers strictly — with the env var unset, `strict = True` (`database.py:7566-7571`) — so it is not a flood of display-less rows. It is four things, one of them live:

- **Registration reads identity out of text on every call** — the four C6 inference lines. Removing them is the point of the effort.
- **`init_project_state` passes `_strict_id_format=False`** (`feature_lifecycle.py:326`), so every project it creates is display-less and turns B8's check red. **Live.**
- **Brainstorm registration raises `EntityIdFormatError`** for any filename stem that doesn't start with a number.
- **The suite has never run the production path.**

**Solved when** the four C6 tuples are struck (`_KNOWN_INFERENCE_SITES` 28 → 24), D5's grep is clean, and `check_display_row_invariant` still reports 0 after real registrations on the new build.

### Measured 2026-09-23 — re-derive before execution

Re-derived at step 0 by `scripts/census_register_sites.py`, the one definition every later step uses. Rev 2's parameter table was still a three-name count (1,113 / 973); it is recomputed over four names below.

Call sites counted by AST walk over `plugins/pd/**/*.py` across **four** names — `register_entity`, `upsert_entity`, `register_entities_batch`, **and `_register_entity_no_display`**. Rev 1 counted three and was wrong by 25 sites.

| | Sites |
|---|---|
| Production, external callers | **13** |
| Production, internal delegations | 3 — `:7814` (inside **`_register_entity_no_display`**, a test-only helper living in production code), `:7874` (`upsert_entity`), `:10698` (`register_entities_batch`) |
| Test / conftest | **1,152** across 48 files at `38935d59`, where C17a's reader fix added one — 1,153 / 49 until `2d654e1a` deleted `test_atomic_promotion.py` and its two sites |

| Parameter | External prod | Internal | Test |
|---|---|---|---|
| `entity_id` | 13 | **3** | 1,137 (151 keyword + 986 positional) |
| `project_id` | **13 — every one** | 2 | 996 |
| `parent_type_id` | **0** | 2 | 99 — **a subset of the 996, not additive** |
| `_strict_id_format` | 1 | 2 | 7 explicit + **25 via `_register_entity_no_display`** |

Counts include positional arguments, not just keywords — all 3 internal delegations pass `entity_id` positionally. Rev 1 counted keywords only for the internal column and reported `0`.


### The experiment, and the hole in it

```bash
PD_REGISTER_ENTITY_STRICT_ID_FORMAT=1 plugins/pd/.venv/bin/python -m pytest \
  plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q -p no:randomly
# 707 failed, 3225 passed, 3 skipped, 44 errors
```

**751 tests across 26 files** depend on identity being optional. Counted by failing *test* (one `--tb=line` cause per test), not by matching output lines:

| Cause | Failing tests |
|---|---|
| `EntityIdFormatError` | **693** |
| assertion-shaped (9 bare `assert`, 5 `AssertionError`) | **14** |

Rev 1 reported "`EntityIdFormatError` ×1,431 against 10 `AssertionError`" and concluded "one defect, 751 times". Both figures were `grep -o` artefacts counting output lines; the conclusion was wrong in a way that matters.

**Thirteen of the 14 are downstream of the same error** — 7 assert on the error text outright, the rest on counts and lookups that fail because registration did. **One is not.** `mcp/test_workflow_state_server.py:4489` registers the *conformant* id `041-nullmeta`, so strict mode writes the display row and `_project_meta_json` returns `id='041'` where the test expects `''`. That is the display-row write path going live — exactly what C5 makes unconditional.

So there is a **second class**, small but real: tests whose expectations encode display-less behaviour. It is not a defect to fix; the test's expectation is what is stale. Step 2 of the build order is where this class surfaces, and it is the only step whose residue is genuinely new behaviour rather than id format.

**The experiment cannot see `_register_entity_no_display`.** Resolution order at `database.py:7566-7573` gives the explicit kwarg precedence over the env var, and that helper hardcodes `_strict_id_format=False` (`database.py:7823`). Proof: `pytest plugins/pd/ui/tests/test_entities.py` with the flag forced on is **91 passed**. Its 25 call sites are therefore absent from the 751 *and*, in rev 1, from the category split. They are category **F** below.

### D1 — Wave 2 sheds two parameters, not four

`_KNOWN_INFERENCE_SITES` (`test_audit_writes.py:532`) attributes exactly four lines in `register_entity` to C6 — `database.py:7575` (regex) and `:7709/:7710/:7711` (slice). `project_id` and `parent_type_id` appear nowhere in it, and correctly so: they are SQL/uuid lookups, not text parses.

**Decision unchanged: Wave 2 removes `entity_id` and `_strict_id_format` only** — at step 5, once no caller passes them (build order, rearranged 2026-09-23). `project_id` and `parent_type_id` defer to **C5b**.

**Rev 1's stated reason was wrong and is withdrawn.** It claimed the aliases carry "1,072 test-site edits on an orthogonal axis". Two errors: the two sets overlap (all 99 `parent_type_id` sites are among the 973 `project_id` sites, so the union is **973**, not 1,072), and **960 of those 973 — 98.7% — also supply `entity_id`** (rev 1's three-name counts; over four names, 983 of 996 — the same 98.7%), landing on lines C5 already rewrites. Deferring does not avoid those edits; it re-opens them. On edit count alone, deferral is the more expensive option.

**The real reason to defer is design risk, not edit count:**

- **7 of 13 external production sites pass `project_id` with no `workspace_uuid`** — `backfill.py:443/:570/:617/:735/:837`, `entity_server.py:474`, `scripts/parse_backlog_md.py:262`. Each needs genuine re-homing design.
- **`project_id` resolves to the wrong workspace in git worktrees.** Rev 2 said it "cannot address 10 of 24 workspaces"; corrected 2026-09-23. Of the 10 with no `project_id_legacy`, 7 are deleted directories. The other 3 are live worktrees of project_illium, and `_compute_legacy_project_id` gives every one of them the repository's root-commit id, so each `project_id`-only write resolves to **project_illium's** workspace. Startup backfill (`entity_server.py:276`) would register a worktree's artifacts there, and MCP `register_entity` with `auto_id` (`entity_server.py:597-624`) takes the number from project_illium's counter but registers the row in the worktree's own workspace. Nothing is damaged yet — the three worktree workspaces are empty. Decision 6 settles which workspace is right; **C17a** implemented it (`833095a9`).
- **`project_id` is not only a workspace alias.** At `database.py:7635-7645` the explicit kwarg is *also* the `entity_created` phase-event label, falling back to `workspaces.project_id_legacy` only when absent. Dropping it changes event metadata on an append-only table. C5b's Verify must assert those labels are byte-unchanged at all 13 sites.

Design work of that shape does not belong in a mechanical codemod wave: its failures would be indistinguishable from the codemod's. Edit count was never the argument. (Rev 2 said "the irreversible wave"; the code is revertible — only data an old build writes during the mixed-version window is not. Calvin L6. The worktree reason in the second bullet is retired: C17a fixed it.)

**C5b scope and dependencies (rev 1 under-scoped both):**

- **`Depends: C7`.** C5b re-touches the same 13 production sites C7 migrates. Rev 1 gave it no `Depends` edge at all.
- **C5b must include the allocator, not just the registrar.** `generate_entity_id(db, entity_type, name, project_id)` (`id_generator.py:92`) has **no `workspace_uuid` parameter**. Remove `project_id` from registration alone and the registrar becomes `workspace_uuid`-only while the allocator stays `project_id`-only — the two halves structurally forced onto different axes, which is the inverse of **C17**'s contract. C5b and C17 are one unit, and both follow **C17a** (decision 6), which makes `project_id` and `workspace_uuid` agree for worktrees before either axis is removed.
- Rev 1 cited `database.py:7315`/`:7332` for the two resolution points, copied from the parent plan and never checked. Both are wrong — the first points at `if self._in_transaction:`. The real sites are **`:7588`** (workspace) and **`:7605`** (parent), as of `2d654e1a`. Re-derive rather than copy — this section's own C7 table exists because the parent plan's line numbers drifted.

### D2 — the signature

```python
def register_entity(
    self,
    entity_type: str,
    *,
    name: str,
    seq: int | None = None,
    slug: str | None = None,
    display_id: str | None = None,
    workspace_uuid=None, project_id=None,          # unchanged, deprecated — C5b
    artifact_path=None, status=None,
    parent_uuid=None, parent_type_id=None,         # unchanged, deprecated — C5b
    metadata=None,
) -> str
```

`upsert_entity`'s signature is byte-identical by contract (feature 109 AC-4.3) and changes in lockstep.

Exactly one of `(seq, slug)` or `display_id`; both or neither raises. Until step 5 the old `entity_id` form stays accepted as a third alternative — still exactly one — so the production callers can move at step 4; step 5 deletes it, leaving the signature above.

- **`(seq, slug)`** — sequence kinds. `entity_id = render_display_id(entity_type, seq, slug)`. Display row written **unconditionally**.
- **`display_id`** — `NON_SEQUENCE_KINDS` only, stored verbatim, no display row (D3).

**Why `display_id` is not the alias C5 forbids.** The "No alias" clause exists to stop a *parsed* alias hiding in a `_migration_13_*`-named helper where the audit auto-approves it. `display_id` is never parsed and is rejected for every sequence kind.

**The `display_id` path has two callers, both filename-stem sourced** (rev 1 claimed one, from a single site it did not sweep):

| Site | Source |
|---|---|
| `entity_status.py:190` | `.prd.md` stem from the brainstorms directory scan |
| `backfill.py:837` (`_register_brainstorm`) | `_brainstorm_stem`, same shape |

`backfill.py:837` is a mechanical edit (`entity_id=stem` → `display_id=stem`). Its parent is set by a separate `_safe_set_parent` call after the upsert, not through a `register_entity` parameter, so D1's deferral does not touch it. (Rev 2 called it a design decision; calvin L7.)

`entity_type` keeps its name — `kind` equals the old `entity_type` value and result dicts carry both as aliases, so renaming would churn 1,152 sites for nothing.

### D3 — B8's invariant must be restated, and its enforcers swept

Under D2 a brainstorm registered after cutover has no display row and is not legacy, so `check_display_row_invariant` goes red on the first brainstorm reconciliation.

**Restated:** every entity has an `entity_display` row unless `is_legacy = 1`, **or its `kind` is in `NON_SEQUENCE_KINDS`**.

**This is the third exemption clause, not the second.** `checks.py:625-628` already loops `for flag in ("is_legacy", "is_deleted")`, and `is_deleted` has no immutability trigger and no silencing test. Rev 1 described the kind clause as the second exemption and did not notice the existing one.

**Sweep targets — prose, SQL, operator text, and tests. Rev 1 listed only the first.**

| Location | What stales |
|---|---|
| `doctor/checks.py:570` | the check's docstring |
| `doctor/checks.py:625-655` | **the SQL itself**, plus the `message` and `fix_hint` operator text, which both say "no entity_display row and is not marked is_legacy" |
| `doctor/__init__.py:35` | check-registry comment |
| `doctor/test_checks.py:2227`, `:2270`, **plus 7 further tests in that file** | test docstrings and assertions restating the invariant |
| `database.py:6390`, `:6393` (migration-7 docstrings), `:6438` (`_census_max`'s) | `:6393` asserts the display row is written "only `if strict:`", false once C5 lands |
| `database.py:6411-6413` | the trigger's ABORT message |
| **parent plan `## C3`**, and this document's own C3 line under Wave 3 | C3's guard predicate refuses buckets holding display-less non-archived rows — post-D3 brainstorms are display-less **by design** |
| `clean_break.py:92-97` | `select_legacy_entities` docstring restating "display-less + not legacy is a bug, not history" |

**Swept at step 3** (`48903e98`, `7fb22edf`), except the trigger's ABORT message, which stays: it names the invariant without restating its exemptions (`… do not use it to silence the display-row invariant`), and `CREATE TRIGGER IF NOT EXISTS` would give new text only to new files. This document's Wave 3 C3 line already carried the restatement; the parent plan's `## C3` got a dated amendment.

**The SQL change re-introduces the column that caused a vacuous green, and must not repeat it.** `checks.py:600-606` records it verbatim: the first version selected `e.kind`, older files raised, the `except` swallowed it, and the check reported green having never run. The existing `cols = PRAGMA table_info(entities)` probe at `:607` handles that — but its documented reading ("a file predating the column has no exempt rows") is **correct for `is_legacy` and wrong for `kind`**: a pre-migration-12 file still holds brainstorms, under `entity_type`. **Interface:** probe for `kind`, fall back to `entity_type` when absent, and never silently drop the clause.

**The only fixture that runs this check cannot reach the new branch.** `_make_db` (`test_checks.py:20`) stamps `schema_version = 9` and its `entities` table has `entity_type TEXT NOT NULL` and **no `kind` column**; `_entity()` (`:2233`) hardcodes `entity_type='feature'` and takes no kind parameter. Both need extending, or the exemption ships with zero coverage. Two red-first tests: brainstorm-without-display passes; feature-without-display still fails.

**The kind exemption is not the `is_legacy`-class hatch.** Since `2d654e1a` nothing at runtime writes `kind`: `promote_entity` was the only writer. The `enforce_immutable_entity_type`/`_type_id` triggers are still absent (dropped at migration 12; `test_database.py:948`/`:2604` pin that), but the `entities` CHECK pairs `type` with `kind` (`type='brainstorm' AND kind='brainstorm'` / `type='work' AND kind IN (…)`), so every single-column route into `NON_SEQUENCE_KINDS` is blocked — verified on a scratch copy of the live DDL, never the live file. Muting a row would take deliberate two-column SQL (`SET type='brainstorm', kind='brainstorm'`), which nothing in the codebase does. **Add one red-first test** asserting a single-column re-kind into `NON_SEQUENCE_KINDS` raises `IntegrityError`. With no runtime writer left, a `type`/`kind` immutability trigger is now possible — Wave 3, because it is a migration and Wave 2 deliberately has none.

**The 97 existing brainstorm display rows stay.** Measured live: 100 brainstorms, **97** with display rows, all non-legacy; the 3 without are all `is_legacy=1`; 0 violations today. Rev 1 said 96. They hold migration-13 parse-accident values (`20260221-012305-slug` → `seq=20260221`), and `_read_entity_display` (`workflow_state_server.py:371`) **prefers** a present row, so deleting them would flip 97 entities onto its stderr-WARN fallback. Doing nothing is both lazy and safe. **Corrected at step 3:** brainstorms never reach `_read_entity_display`. `_project_meta_json` returns for every kind but feature and project (`workflow_state_server.py:453`), and projects return at `:500`, before the read at `:519`. Deleting the rows would flip nothing onto the fallback. The decision stands: nothing needs them gone, and `scan_entity_ids` reads brainstorms verbatim since step 2. The same routing means brainstorms C7 registers without a display row raise no WARN.

**Stated cost of doing nothing:** `_census_max(kind='brainstorm')` is frozen at seq **20260710** permanently. Inert — nothing allocates brainstorm sequences — but recorded rather than discovered later.

**Row-level exemption was considered and rejected:** `entity_display.seq` is `INTEGER NOT NULL`, so a NULL-seq marker needs a migration and would break this wave's "no migration" rollback property.

### D4 — the test migration is a codemod with a repo-wide completeness gate

| | Category | Sites | Treatment |
|---|---|---|---|
| **A** | round-trips exactly through `render_display_id` | **299** | Pure codemod; id unchanged. |
| **C** | non-sequence kind (brainstorm) | **42** | `display_id=` at step 3. **6** pass the strict regex and stay byte-identical; **36** (31 distinct) do not, and would turn step 2 red, so step 1 rewrites them to `20260101-{n:06d}-{slug}` — the shape production brainstorm stems have — through the same mapping and sweep as B (calvin L9). |
| **B** | id must change | **675** | Codemod + reference sweep. |
| **D** | dynamic (f-string / variable / expr) | **96** | Step 1 rewrites the ids strict rejects, from the expressions census 1a emits; call shape by hand at step 3. |
| **E** | no `entity_id` argument | **15** | 13 `register_entities_batch` calls, ids in dicts: step 1 rewrites those strict rejects (census 1a emits them), step 3 swaps the dict keys. 2 MCP `auto_id` calls, which carry no id. |
| **F** | **via `_register_entity_no_display`** | **25** | **New in rev 2.** All in `ui/tests/test_entities.py`; 25 distinct ids, none matching the strict regex, 92 in-file references. At step 1 they become ordinary `register_entity` calls, with ids from rule 3. They are UI tests and never reach `_read_entity_display`, so they are not the fallback's coverage (calvin L8). |

Total **1,152** at `38935d59` (C17a's reader fix added one A site). A (299) and 6 C sites keep their ids byte for byte. Only A carries no downstream risk: every C id — the 6 kept and the 36 step 1 rewrites, since both then pass the strict regex — gets a display row once strict is on at step 2 (`if strict:` writes one for any kind, `database.py:7708`) and loses it at step 3, and any test reading it goes red at step 3 and is updated there (calvin L12).

**9 of the 1,152 call the MCP `register_entity` tool, not the database method** — `entity_server.register_entity(…)` in `hooks/lib/entity_registry/test_entity_server.py` at `:77`, `:213`, `:228`, `:243`, `:273`, `:946`, `:959`, `:972`, `:1005` (6 B, 2 E, 1 A). Step 1 treats their ids like any other. Step 3's call-shape codemod skips them: the tool keeps `entity_id` until C7 changes its surface at step 4.

**Rule 3 is the majority case** — of the literal-id sites, **665 have no leading digit** (`P001`, `bs-mixed`, `''`). **The mapping (calvin L3, revised by the stage review):** built once, repo-wide, keyed on **(kind, literal)** over the sorted distinct pairs, so a literal registered under one kind gets one new id in every file. No per-file counter — that would hand one literal two ids in two files. Five step-1 literals are registered under more than one kind — `'a'`, `'b1'`, `'chk-null'`, `'e0'`, `'solo'` — so their call-site arguments map per kind and their bare references go to hand review. A new id steps its seq up while it equals an id already assigned, or a literal registered in a file that also registers the old one. A match only in other files is no collision, and stepping would change the seq the test's id implies; at `38935d59` that steps 24 same-file cases and leaves 38 cross-file-only ones alone. At execution the mapping stepped 10 (kind, literal) pairs, and multi-kind bare references moved wherever every kind mapped to one id (revision note below). Uniqueness is checked against literals only; a collision with an id built at runtime or minted by the allocator goes red at step 1 and is fixed by hand.

| Old shape | Example | New | Precondition |
|---|---|---|---|
| `^(\d+)-(.+)$` | `1-a`, `00010-existing` | `001-a`, `010-existing` | **`seq >= 1`** |
| `^(\d+)$` | `00042` (backlog) | `042-backlog` — `{seq:03d}-{kind}` | `seq >= 1`; the call's kind is a literal |
| no leading digits (**majority, 665**) | `P001`, `bs-mixed` | `001-p001`, `001-bs-mixed` — `001-{slug}`, slug lowercased, each run outside `[a-z0-9]` → `-`, trimmed | slug non-empty |
| brainstorm, rejected by the strict regex | `bs-mixed` (kind brainstorm) | `20260101-{n:06d}-{slug}` — `n` is the literal's 1-based position among the sorted distinct literals registered only as brainstorms (39 at execution, with the ids census entries and the instrumented run added); slug as rule 3 | slug non-empty |

A literal that fails its precondition — seq 0, an empty slug (`''`), a non-literal kind under rule 2 — is **refused and listed for hand review**. Hand review is an outcome of the codemod, not a category.

**`seq >= 1` is load-bearing:** `test_database.py:9317` registers `backlog` with `'000-v1'`. Rule 1 maps it to itself, but `render_display_id('backlog', 0, 'v1')` raises `seq must be a positive int` (`id_generator.py:85`). It stays category **B**, and the codemod refuses it for hand review; an occurrence-only gate would pass it silently because the literal never changed. (Rev 2 said "route it to category D"; D is dynamic ids. Calvin L11.)

**The completeness gate is repo-wide, not per-file.** 86.0% of literal ids are referenced elsewhere in their own file (872 of 1,014 non-empty literals in the 1,151-site census; the 1,015th is the empty string `''`, which no sweep can key on and which therefore goes to hand review), **and 33 distinct literals are registered in two or more files** — `'001-test'` in four, `'f1'` in four, `'child'` in three, `'P001'` in `test_database.py` + `test_frontmatter_sync.py`. A per-file gate cannot see those, and a per-file counter would hand the same literal two different new ids. The repo-wide mapping makes the 33 consistent by construction — independent fixtures and a shared contract both keep working when one literal gets one id everywhere. **What the codemod rewrites and what the gate checks are different (calvin L4).**

- **Rewrite — test and conftest files under `plugins/pd` only** *(narrowed and extended at execution — see the revision note below)* (repo-root `scripts/` is out of scope), in three positions: (1) the id argument of a family call, counting batch-dict values and a literal a test passes to a helper that forwards it to a family call (first hop only); (2) a string constant exactly equal to `{kind}:{literal}`; (3) a bare string constant equal to the literal, only in a file that registers it, only if the literal contains a digit or hyphen, and only if that file registers it under one kind. Every other occurrence goes to a **committed hand-review list**. Rev 2's rule, every constant equal to the literal in every test file, was too broad: at `38935d59` it hits 880 constants in the files that register the literal and **794 in files that do not** (`''` 238, `'a'` 56, `'f1'` 43, `'p1'` 42, …), and `test_clean_break.py`'s `'P001'` is a legacy-id parse input that must keep its text.
- **Gate:** *(scoped to registering files at execution — see the note below)* afterwards, a token-bounded match (the neighbouring characters are not `[A-Za-z0-9_-]`) over every string constant in those files must find **zero** hits for old literals containing a digit or hyphen, outside a reviewed allowlist recorded as `file:line` plus a one-line reason. Hits for plain-word literals (`child`, `older`) go to hand review, because ordinary English in assertion messages matches too.
- **Non-`.py` files** under `plugins/pd` are scanned as raw text and listed for hand review.
- **Production files** are out of scope: they hold no test ids.

**Substring hazard:** `'1-a'` is a substring of `'1-alpha'`; category F adds `'lim'`, `'older'`, `'newer'`. Replace string **constants** and `f"{kind}:{id}"` composites **via AST**, never `str.replace` over file text.

**Revised at execution, 2026-09-23 (step 1):**

- **Positions 2 and 3 apply only in files that register the literal, and position 2 also covers a `kind:id` token inside a longer string** — SQL, messages, URLs; 85 edits, token-bounded, on parsed string constants, never raw file text. As written, position 2 applied anywhere: 94 of its matches were in files that never register the id, unrelated data such as `test_mermaid.py`'s `"feature:a1"` nodes.
- **The census cannot see every registration.** Ids registered through a loop over kinds, `parametrize`, or a production helper handed a literal (`_process_register_entity`) come from an instrumented suite run that logged every id and the test line behind it. The 21 whose copies are literals are listed in the tool as `ALSO_REGISTERED`. Fixture data that production code parses — backlog rows, brainstorm stems, project folders — is left for a person: *Step 2's list*.
- **A literal registered as a brainstorm and as a sequence kind takes the sequence id for both** (`blocker-x`, `test`), and a bare copy moves when every kind its file registers it under maps it to the same id, so the multi-kind literals mostly moved without hand review.
- **The gate fails only in files that register the id.** Over all test files it found 301 copies; 280 were in files that never register them — mostly short text such as `001`, `p1` and `P001` in legacy-parse inputs, `feature_id` values and raw-SQL rows, which the suite checks. The 19 in registering files are allowed in the tool, each with its reason: artifact paths, display names, prose, one backlog fixture row.
- **Non-`.py` files:** 7 tracked files under `plugins/pd` hold an old id and none needs a change — `uv.lock` hashes, worktree task names in `test-worktree-dispatch.sh`, prose, and `scripts/tests/fixtures/backlog-099-archivable.md`, a legacy backlog row like the backfill fixtures.

### D5 — the exit criterion that cannot be faked

Wave 2 is done when the strict flag is **deleted** — from `database.py`, `hooks/lib/conftest.py:37`, `mcp/conftest.py:31` — *and* `_register_entity_no_display` is gone, and the suite is green.

```bash
rg -l 'PD_REGISTER_ENTITY_STRICT_ID_FORMAT|_strict_id_format|_register_entity_no_display' plugins/pd
test $? -eq 1   # exit 1 = no matches = clean
```

**After step 2** (`bd897969`) the grep lists 13 files, each owned by a later step: `database.py` (the flag and helper, step 5); `feature_lifecycle.py`'s `_strict_id_format=False` in `init_project_state` (step 4); the 7 test call sites passing `_strict_id_format=False` — `test_cleanup_backlog.py` 3, `test_checks.py`, `test_future_file_guard.py`, `test_projection_determinism.py` and `test_census_and_issuance.py` 1 each (step 3's call-shape codemod), plus docstrings saying so in `test_checks.py` and `test_feature_lifecycle.py`; `hooks/lib/conftest.py` with `test_backfill.py` and `test_cleanup_suffix_parsers.py`, the strict-off fixture and its users (step 4); `workflow_state_server.py`, whose `_read_entity_display` docstring names `_register_entity_no_display`; and `doctor/checks.py`, whose docstring names `init_project_state`'s `_strict_id_format=False` (both D3's sweep at step 3). The two conftest line numbers in the first sentence are gone.

**After step 3** (`7fb22edf` on `wave2-core`) the grep lists 10 files. **Step 4:** `feature_lifecycle.py`'s `init_project_state` call and its comment, with `test_feature_lifecycle.py`'s docstring and its assertion that the call passes `_strict_id_format=False`; `doctor/checks.py`, whose docstring, rewritten at step 3, says the text form lasts until C7; `hooks/lib/conftest.py` with `test_backfill.py` and `test_cleanup_suffix_parsers.py`. **Step 5:** `database.py`; `workflow_state_server.py`, whose `_read_entity_display` docstring and caller comment name `_register_entity_no_display`, true until step 5 deletes it; `test_cleanup_backlog.py`'s one deliberate text-form call (step 3's exit guard); `test_structured_registration.py`, whose strict-off `setenv` shows the structured form ignores the switch and proves nothing once the switch is gone. `test_future_file_guard.py`, `test_projection_determinism.py`, `test_census_and_issuance.py` and `test_checks.py` left the list. The step-2 entry put `workflow_state_server.py` and `checks.py` under D3's sweep at step 3; neither mention was false yet, so both moved.

**After step 4** (`d2810833`) the grep lists 3 files, all step 5's: `database.py`; `workflow_state_server.py`, for its two mentions of `_register_entity_no_display`; and `test_structured_registration.py`, for its strict-off `setenv`.

**After step 5** (`c5851605`) the grep lists nothing: `rg` exits 1.

Rev 1 wrote `rg -c … # expect 0`. `rg -c` prints per-file counts and prints **nothing** on a clean tree, exiting 1 — it never emits `0`, so the stated expectation could not be checked. Note `rg` honours `.gitignore`, which correctly skips `plugins/pd/.venv`.

After C6 there is no flag to set, so a green suite with the flag absent is green on the production path by construction. Today that path is reached by **all 13 tests in `mcp/test_issue_spawn.py`** — `:63` sits inside a module-scope `@pytest.fixture(autouse=True)` declared at `:54`, so it applies to the whole file. There is exactly one opt-in *site* repo-wide, which is not the same as one test; rev 1 conflated them. No test passes `_strict_id_format=True`; all 7 explicit sites pass `False`, and 25 more take `False` via the helper.

### ⛔ STOP-THE-WORLD GATE — it guards the moment new code can reach the live plugin

The hazard is a process on the **old build** writing display-less rows once the new build is in place.

**Corrected 2026-09-23 — where the code lives decides what is live, not which branch it is on.** Rev 2 said "branch commits touch no live state". False for anything checked out in the main working tree: `plugins/pd/hooks/sync-cache.sh` runs on every SessionStart (startup, resume, `/clear`) and rsyncs the working tree's `plugins/pd/` into the installed plugin (`~/.claude/plugins/cache/pedantic-drip-marketplace/pd/6.0.0`), which every workspace's hooks and MCP servers load. The live build is the main working tree as of its last sync. **SessionStart is not the only publisher** (stage review, 2026-09-23): Test 12 of `plugins/pd/hooks/tests/test-hooks.sh` runs `sync-cache.sh` with the real `HOME`, from the first ancestor of the hooks directory that holds a `.git` directory. That is how C17a reached the live plugin before any session restarted. Rev 2's evidence, a cache matching the working tree byte for byte, is withdrawn: `rsync -a` copies source mtimes, so a matching cache cannot say which sync wrote it.

- **Steps 0–2 change tests only** (walker, test-id codemod, strict default in the two conftests). Nothing in production runs tests, so they are built in the main working tree on develop.
- **Steps 3–5 change production code.** Build them in `.pd-worktrees/wave2`, a linked worktree nested inside the main checkout. `detect_project_root` only matches a `.git` *directory*, so a session started there, or a `/clear` in this one, resolves to the main checkout and keeps syncing develop. A sibling directory is **not** safe: there the walk finds no `.git` directory and falls back to the worktree itself, which then syncs its own unmerged code.
- The gate runs **before merging steps 3–5 into the main working tree**. The world stays stopped until the new build is published — by the first SessionStart in pedantic-drip or the first hook-gate run after the merge, whichever comes first — and a pd MCP server has started on it.
- **The hook gate publishes.** `test-hooks.sh` run from anywhere in this repository, `.pd-worktrees/wave2` included, syncs the **main checkout's** `plugins/pd/` into the live plugin. While the main checkout holds only steps 0–2, which change tests, that is harmless. After the steps 3–5 merge it *is* the cutover, so from the merge on, run the hook gate only inside the stopped world.

**1. Cue the operator.** Person-in-the-loop by design (decision 4).

**2. Verify, do not assume:**

```bash
ps -axww | grep -i "entity_server\|workflow_state_server" | grep -v grep   # expect no output
lsof ~/.claude/pd/entities/entities.db                                      # expect no output
```

`lsof` alone is insufficient — servers connect on demand. **Verified 2026-09-22 21:31, and again 2026-09-23 before each live write: 0 processes, 0 file holders.** The executing session cannot stop itself; stated exception.

**3. Snapshot after the world is stopped.** `.backup`, never `cp`: the live file is in WAL mode, and on 2026-09-23 its `-wal` still held uncheckpointed writes, which a `cp` of the main file would miss. Verify the snapshot through `file:…?mode=ro&immutable=1`. Plain `mode=ro` is not enough on a WAL-mode file: Python's `sqlite3` (3.53.4) creates `-shm`/`-wal` beside it, and the macOS `sqlite3` CLI (3.51.0) will not open it at all while no `-shm` exists — both reproduced 2026-09-23 on a scratch WAL file. Given a bare path, the CLI opens a snapshot read-write: a `sqlite3 <snapshot> ".backup …"` rehearsal did exactly that and left `-shm`/`-wal` beside `entities.db.pre-c17a-20260923`, and six older snapshots carry them too. To copy a snapshot, back it up from an immutable open:

```python
src = sqlite3.connect('file:<snapshot>?mode=ro&immutable=1', uri=True)
src.backup(sqlite3.connect('<copy>'))
```

**3a. Mark backfill done** (step 4's decision). Do this in the stopped world, after the snapshot and before any MCP server starts on the new build:

```bash
sqlite3 ~/.claude/pd/entities/entities.db "INSERT INTO _metadata(key, value) VALUES ('backfill_complete', '1'), ('backfill_version', '4') ON CONFLICT(key) DO UPDATE SET value = excluded.value;"
```

Then read both keys back. Without this, the first pd MCP server to start runs backfill for its workspace (*Backfill before the gate*).

**4. Restart normally.** Migration 7 (B8's `is_legacy` trigger) does not wait for Wave 2. It reached the live plugin with B8, and the live file is still at `schema_version 6` only because no pd MCP server has started since; the next one to start, in any workspace, applies it. **Rehearsed 2026-09-23** by opening a `.backup` copy of the live registry with `EntityDatabase`, the same open an MCP start performs: schema 6 → 7; entities 579, `is_legacy` 180 and display rows 399 all unchanged; trigger installed and refusing an `is_legacy` UPDATE; integrity ok; 0 foreign-key violations.

**Executed 2026-09-24, on the operator's cue.**

1. **Stopped world:** 0 pd MCP processes and 0 holders of the live file, checked again immediately before the one live write.
2. **Snapshot:** `entities.db.pre-wave2-20260924` by `.backup`. Through an immutable open: integrity ok, 0 foreign-key violations, schema 6, 579 entities (180 legacy), 399 display rows, 523 `workflow_phases` rows, 1,459 phase events, 21 workspaces, 20 cross-workspace parent links (`agent_sandbox/2026-09-24/wave2-gate/baseline.json`).
3. **Rehearsal:** the first MCP start, in `entity_server`'s startup order, replayed on marked copies of the snapshot, once per build. Both wrote the same: schema 6 → 7, the `is_legacy` trigger, and 28 `workflow_phases` rows for backlog items registered since the last start (`backfill_workflow_phases`, which Wave 2 did not touch). Neither changed an entity, a display row or a workspace. The two results are identical table for table, so the cutover's first start writes nothing today's build would not.
4. **Marker (3a):** written to the live file and read back: `backfill_complete=1`, `backfill_version=4`; schema still 6, counts unchanged.
5. **Merge:** `wave2-core` into develop, `fe40082c`.
6. **Publish:** `test-hooks.sh` from the main checkout, 66/66 with 1 skipped. Its Test 12 published the build; the plugin cache matches the merged `plugins/pd` file for file, by content. `./validate.sh` 0/0.
7. **Migration 7 applied 2026-09-24**, on the operator's go-ahead, by the runbook's option A ([2026-09-24-wave2-cutover-runbook.md](./2026-09-24-wave2-cutover-runbook.md)). Result: schema 6 → 7 and the trigger. The quick check read 7, 1, 1, 180, ok. The full check passed 7/7, and entities, display rows and workflow_phases were +0 -0 ~0, with phase events at 1,459 before and after, as the runbook's rehearsal of option A predicted. Its workflow_phases line also printed "rehearsal predicted +28"; that figure is the MCP-start rehearsal, which option A does not run. The first attempt at each check failed with "unable to open database file". The migration's close had left no `-wal` or `-shm`, and the macOS `sqlite3` CLI and the pyenv `python3`, both on SQLite 3.51.0, will not open a WAL-mode file without `-shm` (gate step 3). Both checks now pick the read-only mode by whether a `-wal` file exists.

**Corrected 2026-09-24, after the gate:**

- **Step 4's premise does not hold today.** The pd plugin is disabled at user level: `~/.claude/settings.json` sets `"pd@pedantic-drip-marketplace": false`, and no workspace's project settings turn it back on.
- **No new session applies migration 7.** No session starts a pd hook or MCP server, so the migration is applied deliberately, as the runbook's option A. The plugin cache also has no `.venv` for its MCP servers to start from. pd's own logs were last written on 2026-07-25, the v6.0.0 release.
- **The gate held regardless.** While pd is disabled, no SessionStart runs `sync-cache.sh`, and `test-hooks.sh` Test 12 is the only publisher. That is the publish step 6 records, and it made the world's "stopped" state trivially true.

### Build order — never red

Rev 1 ordered the work C5 → C7 → codemod → C6 and accepted ~751 red tests across three steps. **That red window was never necessary.** The strict gate at `database.py:7575` only *rejects* non-conformant ids — conformant ones already pass today — and no display row is written either way while `strict` is false (`:7708`). So the id migration is independently shippable **green, right now**, before any signature change. Rev 1's "red is expected and is the point of using a branch" was an assertion, not a justification.

Each step below diffs against a green predecessor, so every failure is attributable to the step that caused it. Steps 0–2 run in the main working tree; steps 3–5 in `.pd-worktrees/wave2` (see the gate).

| # | Step | Gate |
|---|---|---|
| **0** ✓ | **DONE 2026-09-23.** Walker `scripts/census_register_sites.py`, checked by `scripts/test_census_register_sites.py`: a synthetic fixture with one call site per category A–F, and each of four mutants (every id round-trips, no F check, positional ids ignored, delegations counted as callers) fails it. The headline counts are measurements, not the check: they have already moved twice: 1,153 → 1,151 when `2d654e1a` deleted a test file, and 1,151 → 1,152 when `38935d59` added one. Baseline **re-captured at `38935d59`** by `scripts/capture_test_manifest.sh` into `agent_sandbox/2026-09-23/wave2-step0/` (gitignored — regenerate from `COMMIT` if lost; `ENV` records cwd, rootdir and the python/pytest/sqlite versions): `collected.txt` (4,027), `outcomes.txt` (4,024 passed, 3 skipped), `strict-all.txt` (746 failures and errors under forced strict, 732 naming `EntityIdFormatError`), `strict-nonformat.txt` (the other 14 — the same 14 as the first capture at `3305e0e8`; 13 are id-format fallout whose message does not name the error). | green, unchanged |
| **1** ✓ | **Make every test id valid under strict, before strict is on.** **No signature change.** Rewriting call-site literals is not enough: at `38935d59`, **136** of the 732 forced-strict `EntityIdFormatError` failures name an id that is no B/F/C call-site literal — built at a D site (`f"perf-{i:03d}"`, `test_workflow_state_server.py:1133`), carried in a `register_entities_batch` dict (`'batch-001'`, `test_register_upsert_split.py:340`), or handed to a test helper that forwards it (`_register(db, "initiative", "i1", …)`, `test_rollup.py:260`). By file: `test_entity_engine.py` 53, `test_database.py` 17, `test_workflow_state_server.py` 16, and `test_entity_lifecycle.py`, `test_event_sourced_state.py` and `test_rollup.py` 10 each. **1a** — extend the census to emit batch-dict ids, D-site expressions and first-hop helper literals, and to mark the 9 MCP-tool calls (D4). **1b** — codemod to **round-trip form**, exactly `render_display_id`'s output with seq ≥ 1, over B, F, 36 of C, and every D/E/helper id strict rejects, plus D4's reference sweep. The 25 F calls switch from `_register_entity_no_display` to plain `register_entity` — with strict still off that changes nothing — so the forced-strict run covers their ids too. "Conformant" is the weaker strict regex: `'1-a'` passes it and still becomes `'001-a'` here, so step 3 changes no id (calvin L2). **Exit:** suite green; the forced-strict run has no failure caused by an id format, and every failure left is listed with its reason — that list is step 2's; D4's gate clean outside its allowlist; the census test passes; a new manifest captured. **DONE 2026-09-23** (`62c00166` tooling, `995573ba` rewrite): 2,222 constants in 34 test files from one mapping of 571 (kind, literal) pairs, 10 stepped past a collision (`scripts/wave2_step1_mapping.tsv`), plus 74 hand-edited lines. Default suite unchanged — 4,027 collected, 4,024 passed, 3 skipped — with 2 node ids renamed. Forced strict 746 → 26, named under *Step 2's list*. Census after: A=994, B=1 (the deliberate empty id), C=46, D=96, E=15, F=0. Gate: 0 unexplained, 19 allowed (D4, revised at execution). | green |
| **2** ✓ | Delete both conftest `setdefault`s so strict defaults on. The residue is exactly the list step 1's exit left — 26 tests in four classes, named under *Step 2's list*, two of which need a decision first; fix each entry, and any failure outside that list **stops the step** (calvin L13, revised: the step-0 baseline's 14 were measured before step 1, and 13 of them are id-format fallout step 1 removes). Add the one deliberate test for `_read_entity_display`'s fallback — a legacy feature row with no display row, asserting the WARN and the metadata fallback — since strict mode removes the accidental coverage it has today (calvin L8). **DONE 2026-09-23** (`bd897969`), with the operator's two decisions on *Step 2's list*: the 21 backfill tests run strict-off through `_strict_id_format_off_until_c7` (hooks/lib/conftest.py) until step 4, and `scan_entity_ids` got its production fix here. `mcp/conftest.py` held only the default and is deleted; `test_issue_spawn.py`'s strict opt-in went with it. `test_audit_writes.py`'s inventory rebased +2 for `database.py`'s new import. Suite 4,029 collected, 4,026 passed, 3 skipped; forced strict 0 failures. Delta against step 1: one rename (the empty-id test now asserts rejection) and two new tests (the brainstorm branch of `scan_entity_ids`, `_read_entity_display`'s fallback). Published to the live plugin by the hook gate — the only production change is read-only. | green |
| **3** ✓ | **Opens with the import probe:** a planted `raise RuntimeError` at the top of the worktree's `database.py` must turn the worktree suite red at import, then comes out — if it stays green, the tests run the main checkout's code and nothing after counts (calvin L5). Then **C5, additive**: `seq`/`slug`/`display_id` join `entity_id`, and a call passes exactly one form; the new form writes the display row unconditionally, while the `entity_id` form keeps today's `if strict:` path untouched until step 5. With it, **D3's restated invariant + its eight sweep targets + the fixture extension** — **and, in the same commit, the call-shape codemod over test files**: every test call to `seq=`/`slug=` (C to `display_id=`), `name` as a keyword, `register_entities_batch` dicts the same way; D and E by hand (calvin L1). It skips the 9 calls to the MCP `register_entity` tool, which keeps `entity_id` until step 4 (D4). **Exit guard:** the census finds no test call passing `entity_id` outside those 9 — otherwise a test could stay green on the old form until step 5 deletes it. Record the `plugins/pd/scripts/` scan-root decision (calvin L15). **DONE 2026-09-23** on `wave2-core` (`48903e98` C5 + D3, `416f5fdb` codemod, `dfe2eba1` and `7fb22edf` tidy). The probe's planted `raise` failed collection across the worktree suite, so the worktree runs its own code. C5 and the codemod are separate commits: C5 is additive, so `48903e98` is green without the codemod; the same-commit rule dates from the draft where step 3 removed `entity_id`. The codemod (`agent_sandbox/2026-09-23/wave2-step3/rewrite_call_shape.py`, one-shot and not committed; the census's exit check is the lasting gate) rewrote 48 test files: literals to `seq=`/`slug=` or `display_id=`, and D ids through the new `identity_kwargs(kind, display_text)` in `entity_registry/test_helpers.py` rather than by hand. Hand fixes: the empty-id test now asserts an empty slug is refused; `test_census_and_issuance.py`'s `_seed` deletes the display row a structured call now writes when it seeds a legacy shape; four `test_engine.py` loops numbered from 0, which strict's `^\d+-` let through as `000-…` and `render_display_id` refuses. **Exit guard: one test call still passes `entity_id`, deliberately.** `scripts/tests/test_cleanup_backlog.py`'s archival test registers a slugless legacy backlog id (`99001`), which structured identity cannot express; step 5 deletes the text form and must seed that row directly. D3: all eight targets swept but one (see D3). Scan-root decision: `plugins/pd/scripts` joined `_INFERENCE_SCAN_ROOTS`, adding no site. The inference lint rebased its four `database.py` tuples (`:7577` → `:7642`, `:7711-7713` → `:7778-7780`). Suite at `dfe2eba1`: 4,044 collected, 4,041 passed, the same 3 skipped; forced strict 0. Delta against step 2: one rename (`test_entity_id_empty_string_rejected` → `test_empty_slug_rejected`) and 15 new tests — 10 in `test_structured_registration.py` and 4 in `test_checks.py`, all red first, plus the `kind` pin, green since migration 12. Census: 1,162 test sites, A=7 (MCP-tool calls), D=1 (the exception), E=1,154. | green |
| **4** ✓ | **C7-prod** — 13 external sites + the 3 upstream contracts; with the tool surface, the 9 MCP-tool test calls step 3 skipped and the command files that call the tool (found at step 3, after *C7's upstream contracts*). `entity_server.py:474`, the registration inside `_process_create_key_result`, is the one production site no test reaches — its only test covers the missing-parent error, raised before registration — so a registering test comes first. After this step nothing passes `entity_id`. **DONE 2026-09-23** on `wave2-core` (`d2810833`), as sorted under *Step 4 classified*. `generate_entity_id` returns `(seq, slug)`. The MCP tool takes `seq`/`slug`/`display_id`, and `allocate_entity_id` also returns `slug`. Both command files register with the allocated seq/slug. The lifecycle functions refuse, before any write, an id the allocator would not render. `create_key_result` works now: its registering test came first and failed on the metadata bug, which is fixed along with a real allocation. Legacy ids are skipped and logged through `registration_identity` (`id_generator.py`); tests go through `identity_kwargs`, which raises instead. `seed_legacy_entity` (`test_helpers.py`) writes pre-cutover rows directly, which removed the 21 strict-off tests and `test_cleanup_backlog`'s deliberate text-form call. Backfill was run against the live registry and needed five fixes (*Backfill before the gate*). Suite: 4,065 collected, 4,062 passed, the same 3 skipped; forced strict 0. Delta against step 3: one rename (`test_project_id_bypasses_strict_display_gate` → `test_project_registers_with_seq_and_slug`) and 21 new tests; everything that passed at step 3 still passes. Census: 0 test calls pass `entity_id`; E=1,167. Inference lint rebased (`backfill.py:756` → `:795`, `feature_lifecycle.py:97` → `:98`). Step 1's `rewrite_test_ids.py --check` now lists 5 slugs in `test_server_helpers.py` that match old ids (`orphan-ws` became `001-orphan-ws` and then `slug="orphan-ws"`). That tool's job ended at step 1, and step 6 does not re-run it. | green |
| **5** ✓ | **C6, plus C5's removal half** — delete `entity_id` and `_strict_id_format` from `register_entity` and `upsert_entity` (D1), the 4 inference lines, the strict flag, and `_register_entity_no_display`. Nothing passes or calls them after step 4, so this is pure deletion, and D5's grep proves it. **DONE 2026-09-24** on `wave2-core` (`c5851605`). Deleted: `entity_id` and `_strict_id_format` from `register_entity` and `upsert_entity`, and the `entity_id` key from `register_entities_batch`; `_structured_identity` now has two forms; `PD_REGISTER_ENTITY_STRICT_ID_FORMAT`, `_ENTITY_ID_FORMAT_RE`, `EntityIdFormatError`, `_register_entity_no_display`, and the slice parse that filled the display row from the text form. Inference inventory: the four C6 tuples are struck and `_INVENTORY_HIGH_WATER` drops from 28 to 24. Six sites are rebased for line shifts: `workflow_state_server.py:485/707/1147/1429` moved up one line, and `database.py:4199/4262` became `:4163/:4226`. There are no new sites. D5's grep (`rg -l … plugins/pd`) exits 1. The comments that named the deleted helper or switch are rewritten, and `CHANGELOG.md` gets Unreleased entries. `capture_test_manifest.sh` drops the forced-strict pass, which would now just repeat the plain run, so step 5's manifest has no strict files. The census and step 1's rewrite tool no longer read the regex from `database.py`. The census now counts 2 internal delegations instead of 3, because the helper's is gone. Suite: 4,065 collected, 4,062 passed, 3 skipped, the same node ids as step 4. | green |
| **6** ✓ | Gates + D5's grep + the end-to-end manifest check, step 0 → step 5. **DONE 2026-09-24**, on `9fb4f2a7` after the review round (*Review — one pass, one fix round*). Gates: the 3-path scope 4,022 passed, 3 skipped; `plugins/pd/scripts/tests` 49; scripts plus audit 56; `./validate.sh` 0/0; the census and rewrite-tool tests 3; D5's grep exits 1. The end-to-end manifest runs step 0 → step 6 (`agent_sandbox/2026-09-23/wave2-step6/`), because the review round added a commit: 4,027 → 4,074 collected, +51 −4. The 4 are the recorded renames: step 1's two `msg-probe` ids, the empty-id test (renamed at steps 2 and 3), and step 4's project test. Every other test that passed at step 0 still passes. The hook gate (`test-hooks.sh`) is not run here: it publishes the main checkout, so it runs inside the stopped world after the merge. | green |

**Steps 3–5 rearranged 2026-09-23 — add first, delete last (the operator's decision).** As first written, step 3 removed `entity_id` while the 13 production callers kept passing it — all by keyword — until step 4. An instrumented run at `38935d59`, a pytest plugin recording which tests reach a family call from production code, found at least **95 tests in 10 files** going through 12 of those 13 sites, so step 3 could not be green. Two smaller breaks had the same cause: `_register_entity_no_display` (`database.py:7790`) passes both removed parameters, and the unconditional display write replaces the `if strict:` block (`database.py:7708`) that holds three of the four lines step 5 deletes (`:7709-7711`), so the exact-set inventory lint would fail at step 3. Rejected: merging steps 3 and 4, which puts C7's design work — `generate_entity_id`'s return, two MCP tool surfaces, the upsert conflict lookup — into the codemod's commit, the mix D1 rejects for C5b; and accepting red at step 3, rev 1's window. The two-form signature exists only on the worktree branch: steps 3–5 merge together through the gate, so it never reaches develop or the live plugin.

### Step 2's list — what step 1 left under forced strict

Captured at `995573ba` (`agent_sandbox/2026-09-23/wave2-step1/strict-all.txt`, regenerate with `scripts/capture_test_manifest.sh`). 26 tests, four classes; none is a test's own id any more.

- **Backfill registers raw legacy ids read from fixture data — 21. Decided 2026-09-23: strict-off until step 4.** `backfill.py:443` passes a `backlog.md` row's first cell (`00019`) as `entity_id`; brainstorm stems (`plan`, `some-plan`) and a `.meta.json` project (`P001`) arrive the same way. Production's strict default rejects them too: on a workspace whose backfill has not completed, every MCP start logs `entity-server: backfill failed` at the first legacy row (`entity_server.py:274-278` catches it), and this repo's and fractorg's `docs/backlog.md` rows are all five-digit. The fix is C7's — these are three of its 13 sites — so it lands at step 4. Tests: `test_backfill.py` 19 (TestBackfillCompleteMarker 4, TestBacklogTitleTruncation 4, TestParentDerivation 4, TestOrphanedAndExternal 3, TestScanOrder 2, TestBacklogStatusDerivation 1, TestIdempotencyAndPriority 1) and `test_cleanup_suffix_parsers.py` TestACCL2BackfillNoMarkerDerivation 2. Options: pin these 21 to strict off until step 4, which D5's grep then forces out by step 5; or give their fixtures conforming ids and lose the legacy-format coverage.
- **`scan_entity_ids` drops the zero-padding — 2. Decided 2026-09-23: fixed at step 2.** Once display rows exist it rebuilds ids as `f"{seq}-{slug}"` (`database.py:10443`), so `001-scan-1` reads back as `1-scan-1`. No production code calls it. Render through `render_display_id` or delete the method — a production change, and step 2 runs in the main checkout; it only reads, so publishing it early writes nothing. `test_database.py::TestUtilityMethods::test_scan_entity_ids_returns_ids`, `TestProjectScopedQueryListEntities::test_project_scoped_query_scan_entity_ids`.
- **A deliberate empty id — 1.** `test_database.py::TestBoundaryEntityIdEmpty::test_entity_id_empty_string_registered` registers `''` on purpose. Strict rejects it, rightly, so the test asserts `EntityIdFormatError` instead.
- **Display-row expectations — 2.** `test_workflow_state_server.py::TestProjectMetaJson::test_null_metadata_uses_empty_dict` expects id `''` and gets `041`. `test_entity_status.py::TestReconciliationIsNonDestructive::test_missing_display_row_and_missing_source_survive` needs a row with no display row, which strict registration cannot make; step 1 fixed its precondition query, which had named an id no row carried and so passed vacuously.

**The node-id manifest is not optional, and it is the one place the Risks section's "assert shapes, not counts" is suspended.** After a machine rewrite of 675+ call sites, "suite green" is satisfiable by a suite that tests strictly less — a codemod that deletes, renames, or collapses a test passes step 6 exactly as well as a correct one. Every step from 1 on captures a manifest and compares it with its predecessor's: `passed_after ⊇ passed_before` **by node id**, and `collected_after == collected_before`, both modulo an enumerated delta with a one-line reason per entry. Step 6 repeats the check from step 0's manifest to step 5's, against the concatenated deltas. Deltas are expected where steps 3 and 5 delete tests along with the code they cover. Step 1's delta was 2 renames, not the none this paragraph expected: `test_router.py`'s two parametrize ids embedding `msg-probe-1`/`msg-probe-2`, which moved once the instrumented run showed them registered — the pre-execution count assumed that file untouched. These are counts diffed against a manifest taken on the same tree, not measurements of the shared live registry, which is what that Risks rule actually governs.

Capture with `scripts/capture_test_manifest.sh <out-dir>` at every step — the one definition, as the census walker is for call sites. It runs the four scopes in **one** pytest process from the repo root, because the conftests' strict-off default is session-scoped and process-wide: `ui/tests` or `scripts/tests` run on their own are strict, so their outcomes are not comparable. It also records `COMMIT` and `ENV`. It fixes the two capture bugs step 0 hit: zsh does not word-split `$SCOPES`, which once gave "no tests ran", and piped pytest cuts summary lines at 80 columns, which twice dropped the exception text (hence `COLUMNS=1000`). `collected.txt` node ids are rootdir-relative and the other files cwd-relative, so compare like with like. `scripts/test_census_register_sites.py` is outside the four scopes; run it separately.

**`_KNOWN_INFERENCE_SITES` needs an explicit rebase step, twice.** It is an EXACT-SET lint on `(path, lineno, idiom)` (`test_audit_writes.py:573`) — it fails on any line shift, not only on added or removed sites. Steps 3 and 4 shift `workflow_state_server.py:485/:707/:1147/:1429` and `backfill.py:756`. Step 3 changed neither file; it rebased the four `database.py` tuples instead, so both shift at step 4. Step 5 must additionally strike the four C6 tuples and **lower `_INVENTORY_HIGH_WATER` from 28 to 24** (`:626`; done at step 5, then raised to 25 at the review, which declared `registration_identity`), whose comment says it moves down when a site is removed and never back up. Run `pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q` after **each** of steps 3, 4 and 5 — the same rebase was already required for C23 and again for C1/C2 in this campaign.

**Every step's gate includes `plugins/pd/scripts/tests`.** Seven family call sites live under `plugins/pd/scripts` — `parse_backlog_md.py:262` plus 6 test sites (5 before `38935d59`) — and that directory is outside the 3-path suite the Gates section flags as historically missed. A codemod regression there would otherwise surface only at step 6.

C7's upstream contracts — the parent plan's three, plus `register_entities_batch`, whose dicts carry an `entity_id` key (calvin L1):
- `generate_entity_id()` (`id_generator.py:92`) returns a string and discards `seq`/`slug`. It must return both.
- **Two** MCP tool surfaces expose `entity_id`, not one: `register_entity` (`entity_server.py:515`, param at `:517`) and `create_key_result` (`:1419`, param at `:1424`). Both become `seq`/`slug`. Rev 1 cited `:475`, which is a `db.register_entity(...)` **call site** inside `_process_create_key_result` (`:449`) — correct in the C7 drift table, wrong as a tool surface, and it hid the second tool entirely.
- `upsert_entity`'s **conflict lookup** (`WHERE workspace_uuid = ? AND type_id = ?`) moves to structured identity without breaking three-branch insert-or-update semantics.

**Found at step 3 — command files call the tool, and this plan never listed them.** `create-feature.md:20` and `create-project.md:19` pass the allocated `entity_id` to `register_entity`; `add-to-backlog.md:13` passes `auto_id`. A `seq`/`slug` surface needs the slug, and `allocate_entity_id` (`entity_server.py:633`) returns only `seq` and `entity_id`. `create-project.md:19` also registers a backlog entity from a `*Source: Backlog #NNNNN*` marker: a slugless five-digit id, the legacy-id question backfill raises. `plugins/pd/README.md:124` documents the tool. All of it moves at step 4, with the tool.

**Step 4 classified; the legacy-id question decided (2026-09-23, the operator).** Eight of the 13 sites move without a design choice. `feature_lifecycle.py:205/:317` take `seq`/`slug` from their parameters. `task_promotion.py:367` and `entity_server.py:858` go through `generate_entity_id`, which returns `(seq, slug)`. Brainstorm stems at `entity_status.py:190` and `backfill.py:837` become `display_id=`. `server_helpers.py:278` moves with the MCP tool, and `allocate_entity_id` also returns `slug`. `entity_server.py:474` takes a real allocation. Five sites read ids with no seq/slug form: `backfill.py:443/:570/:617/:735` and `scripts/parse_backlog_md.py:262`. These are five-digit backlog ids (`00019`, and fractorg's `00019-slug`), `P001` projects and placeholder parents. **Decided: skip and log.** Each such id is skipped with one stderr line; there is no legacy registration path. `create-project.md` links an existing `#NNNNN` backlog row instead of registering one. Structured identity also fixes backfill's re-runs, which rebuilt ids from `str(row["seq"])` (`43-slug`, missing the real `043-slug` row). **Consequence:** backfill today stops at the first legacy backlog id, because `run_backfill` does not isolate its scanners and `ENTITY_SCAN_ORDER` puts backlog first; the live registry has no `backfill_complete` key. After step 4 it completes for the first time, so before the gate it runs against a `.backup` snapshot of the live registry and the operator sees what it writes. Its `backfill_complete` marker is one global `_metadata` key, so the first workspace to finish stops every other workspace's backfill. That is pre-existing, out of scope, and recorded here. **Found while classifying:** `create_key_result` has never worked. It passes `validate_metadata` a JSON string (`AttributeError`, on develop too), and strict mode refuses its name-derived id. Step 4's registering test fails on both.

### Backfill before the gate — found at step 4

Skip-and-log lets backfill finish, which it has never done on the live registry. So step 4 ran it against a `.backup` snapshot, once for each of the 9 workspaces with a `docs/` folder. The done-marker is global, so whichever workspace starts first is the one that runs. The first runs found five defects that the backlog crash had hidden. Each is now fixed, with a red-first test in `TestBackfillLeavesTheRegistryAlone`:

1. **The NULL-phase cleanup marked every workspace's rows finished.** That was 33 rows, 30 of them `planned`. It now stays in its own workspace and touches only completed or abandoned entities.
2. **Parents read from files replaced parents set later** (`feature:111` lost `project:P003`). Backfill now only fills a missing parent.
3. **A `brainstorm_source` that was a type_id, or that named a non-brainstorm file, minted phantom brainstorms** (`brainstorm:brainstorm:…`, `brainstorm:prd`). A type_id is now used as-is, and an in-repo path outside `brainstorms/` gives no parent. **Corrected at review (2026-09-24):** the fix was incomplete. Every absolute path still counted as external, so terry_agent's absolute `…/docs/projects/P001-…/prd.md` still minted `brainstorm:prd`. A path under `artifacts_root` is now in-repo, and an in-repo brainstorm missing from disk is `orphaned`, not `external`.
4. **A placeholder parent overwrote a real row's status with `orphaned`.** This happened when the id exists in two workspaces, because `get_entity(type_id)` returns None when it is ambiguous. There are 7 such type_ids live; in terry_agent it hit 2 active brainstorms. Placeholders now register only when absent. The root cause was the unscoped lookup, which item 6 fixes.
5. **fractorg would have had 22 features registered twice.** Its registry holds unpadded ids (`feature:66-x`) where `.meta.json` says `066`. Rows are now matched by (seq, slug) first.
6. **Found at review (2026-09-24): parents were linked across workspaces.** The unscoped `get_entity` failed in two ways:
   - When the only row with a type_id belonged to another workspace, it returned that row. Once fractorg's own legacy rows were skipped, its brainstorms citing `#00015`/`#00033`/`#00034` were linked to pedantic-drip's backlog rows.
   - When a type_id exists in two workspaces, it returned None, so the link was silently dropped.

   Every backfill lookup and `set_parent` call is now scoped to the workspace being backfilled, which is resolved once before any write.

After the fixes (final state: snapshot run 4, after the review round):

- **4 workspaces:** nothing changes but the marker.
- **cast-below:** 1 parent filled, pointing at its own legacy `project:P001`. The unscoped lookup could not find that row, because `project:P001` exists in several workspaces.
- **pedantic-drip:** 1 phase set on a done feature, 5 parents filled, 13 renames, and 4 brainstorms from `docs/brainstorms/*-source.md`. The scanner's `.md` phase registers those by design.
- **fractorg:** 10 renames. **Corrected at review:** the "3 parents filled" first recorded here were the cross-workspace links of item 6, and they are gone.
- **project_illium:** 28 new entities (24 features, 4 brainstorms) that are on disk but not registered.
- **terry_agent:** 15 new, 3 of them reusing a number that its folders already reuse; the 16th had been `brainstorm:prd`. 3 parents filled, 2 of them the two-workspace brainstorms the unscoped lookup dropped.

**Decided (the operator):** fix all five, and mark backfill done at the gate (gate step 3a), so this identity change registers nothing through backfill. Clearing the key later runs it on purpose. Evidence is in `agent_sandbox/2026-09-23/wave2-step4-backfill-snapshot/` (the `run3-*` and `run4-*` directories).

### Review — one pass, one fix round (2026-09-24)

One reviewer pass over `d39a612d..c5851605` (steps 3–5). **Verdict: not approved** — 2 blockers, 3 warnings, 7 suggestions. Both blockers were checked against the run-3 snapshot DBs before any fix, and reproduced exactly. One fix round, `9fb4f2a7`:

- **Blockers:** item 6 above (cross-workspace parents) and the correction to item 3 (absolute in-repo paths).
- **Warnings:**
  - `skills/decomposing/SKILL.md` is a markdown caller the step-4 tool-surface sweep missed. Steps 3 and 7 now register with the allocated `seq`/`slug` and never use `auto_id`, whose second allocation would break the skill's remap.
  - The inference scanner could not see `registration_identity`'s parse, because it did not match the receiver name. The parameter is now `entity_id`, and the site is declared as `SANCTIONED - round-trip gate for ids read as text`. That raises `_INVENTORY_HIGH_WATER` from 24 to 25, with its line in the table. The parse is not a duplicate of `clean_break.parse_legacy_seq`: that function extracts a number from a legacy id for the census, while this one refuses legacy ids.
  - `allocate_entity_id`'s docstring drops the `P{NNN}` advice and documents `slug`.
- **Suggestions taken:**
  - `name` is keyword-only on `register_entity` and `upsert_entity`, as D2 pins; the two internal delegations had passed it by position.
  - `isascii()` is checked before `int()`.
  - An empty `display_id` reports itself through `_process_register_entity`.
  - The project re-run lookup includes the slug.
  - The lifecycle functions' Raises docs are updated.
  - A docstring note says `upsert_entity` finds conflicts by the rendered type_id only, so a row stored under an older text form of the same (seq, slug) is not found. Backfill checks for such rows first; the other callers allocate fresh numbers.
  - A comment notes that `create_key_result`'s retry can leave a gap in the sequence.
- **Tests:** 9 new. The 4 blocker regressions and the S5/S6 tests all failed first. The `init_feature_state` refusal test pins behaviour that shipped at step 4 without a test.
- **Not re-reviewed**, per the one-pass rule. The red-first tests verify the fixes, and so does snapshot run 4 across all 9 workspaces: no new cross-workspace link, no phantom, no replaced parent, no status change.

### C7's call sites — re-derived, parent-plan line drift corrected

| Site | Plan said | Actual |
|---|---|---|
| `entity_status.py` | :190 | **:190** ✓ |
| `scripts/parse_backlog_md.py` | :254 | **:262** |
| `database.py` (batch delegation) | :10432 → :10727 | **:10698** |
| `feature_lifecycle.py` | :205, :312 | **:205, :317** |
| `entity_server.py` | :471, :853 | **:474, :858** |
| `server_helpers.py` | :278 | **:278** ✓ |
| `backfill.py` | :439, :566, :613, :731, :833 | **:443, :570, :617, :735, :837** |
| `task_promotion.py` | :367 | **:367** ✓ |

Re-derive with the step-0 walker rather than reading these literals. Rev 1 wrote this table and then cited two stale line numbers of its own in D1 — the defect is not hard to repeat.

**`plugins/pd/scripts/` needed a declared decision** (into `_INFERENCE_SCAN_ROOTS`, or explicitly uncovered). `parse_backlog_md.py:262` is a caller the lint will never name. **Decided at step 3: into `_INFERENCE_SCAN_ROOTS`**, which adds no site today.

### Rollback — Wave 2 adds no migration

`V2_MIGRATIONS` ends at **7**, `V2_SCHEMA_VERSION = 7`, and entry 7 is B8's trigger, already shipped. C5/C6/C7 are signature and call-site changes that **add no migration and write nothing to the live registry**. Code rollback is `git revert` in the main working tree, then a session start in pedantic-drip, which syncs the reverted build into the live plugin.

The residual risk is data written by an **old build during the mixed-version window** — what the stop-the-world gate closes. Those rows are identifiable by the existing detector: non-legacy, non-exempt entities with no display row. Remediate only rows created after the cutover timestamp — the merge commit's committer time, which the operator records in this plan when the gate closes (calvin L14).

**Do not restore the snapshot wholesale.** One file holds seven workspaces' entities; a full restore reverts ~153 rows in six uninvolved repos and resets `sequences.next_val` below numbers already materialised as directories and branches — feature counters as of 2026-09-23: 135 pedantic-drip, 115 project_illium, 80 fractorg, 51 terry_agent, 22 cast-below. project_illium's and terry_agent's were raised that day to clear drift, so restoring any earlier snapshot puts both back behind their disk. `/pd:create-feature` hard-stops on that (step 2 of the command); a path without that prose guard would re-mint a number that already owns a directory — the RCA's opening incident. The snapshot is forensic evidence, not a rollback plan.

### Found during review, deliberately out of scope

Both pre-existing, neither caused by Wave 2, neither blocking it:

- ~~**`promote_entity` is type-locked.**~~ **Resolved 2026-09-23 — deleted in `2d654e1a` (decision 5).** The framing here was wrong: its spec allowed only kind changes the `type`/`kind` CHECK permits, and its designed use, backlog → feature, worked. The defect was that it had never been called.
- **`_compute_legacy_project_id`'s docstring is false** (`project_identity.py:811`). It says migration-only, but it is `project_id`'s live source in both MCP servers (`entity_server.py:235`, `workflow_state_server.py:237`) and in `reconciliation_orchestrator/__main__.py:104` and `task_promotion.py:354`. What it hid is D1's worktree misrouting. **Fixed with it in C17a (`833095a9`).**

**Found at the review, out of scope: the live registry already holds 20 cross-workspace parent links.** In every snapshot's `before.db`, 20 children have a parent in another workspace. Backfill no longer adds any, since the review round. These 20 predate Wave 2 and are left for a registry cleanup.

**Found at cutover, out of scope:**

- **`scripts/migrate_db.py migrate` backs up with `shutil.copy2`.** It copies the main file only, so on a WAL-mode registry the backup can miss committed writes. Its check, `integrity_check` plus the entity count, catches lost inserts but not lost updates. `--dry-run` makes the same copy. The fix is the `sqlite3` backup API, which `cmd_backup` in the same file already uses.
- **`~/.claude/pd/memory/memory.db` has no owner.** It is 8 MB, last written 2026-06-21, at its own `schema_version` 7. The semantic-memory subsystem that used it was torn down in `ea0b15e1`, and no code in the repo opens it. Archiving or deleting it is the operator's call.

### Calvin ledger — Wave 2 (2026-09-23)

Run per `~/.claude/CLAUDE.md` before executing Wave 2: three rounds, the author (the agent that wrote this section) adjudicating. Line numbers are the document's physical lines at the time of the run, before the answers below were written back. Every RESOLVED answer is applied in the text above.

| # | Line | Quote | Category | Question | Status | Author's answer |
|---|------|-------|----------|----------|--------|-----------------|
| 1 | L508 | "**C5** — signature, unconditional display write" | completeness · blocker | Which step rewrites the 1,113 `entity_id` call sites, and how is step 3 green without that? | RESOLVED | Step 3 carries a second mechanical codemod in the same commit: every call site becomes `seq=`/`slug=` (C becomes `display_id=`), `name` becomes a keyword, `register_entities_batch` dicts swap their `entity_id` key the same way. Mechanical because step 1 already made every id round-trip. D and E by hand in the same commit. |
| 2 | L506 | "Codemod ids to conformant form" | inconsistency · blocker | Is "conformant" the same as "round-trips"? What does step 1 leave `'1-a'` as? | RESOLVED | No. "Conformant" is the strict regex `^\d+-.+`; step 1 targets round-trip form (exactly `render_display_id`'s output, seq ≥ 1), so `'1-a'` becomes `'001-a'` at step 1 and step 3 changes no id. |
| 3 | L445+L450+L451 | "per-file counter + slug from old text" | completeness · blocker | What exactly is the output for `'P001'`, `'bs-mixed'`, `''`, `'00042'`? | RESOLVED | One repo-wide mapping over sorted distinct literals. Rule 1 `{seq:03d}-{slug}`; rule 2 `{seq:03d}-{kind}`; rule 3 `001-{slug}` (lowercase, non-`[a-z0-9]` runs → `-`, trimmed); seq steps up on collision with a literal or an assigned id; seq 0, empty slug and a non-literal kind under rule 2 go to hand review. No per-file counter. Drill: uniqueness is checked against literals only; runtime collisions go red at step 1 and are fixed by hand. |
| 4 | L455+L457 | "zero occurrences of each old literal" | ambiguity · blocker | What is an occurrence? | RESOLVED | Rewrite: test/conftest constants equal to the literal or to `{kind}:{literal}`. Gate: token-bounded match over those constants, zero hits for literals with a digit or hyphen, hand review for plain words; non-`.py` files are raw-scanned for hand review; production files are out of scope. |
| 5 | L479 | "Build them in `.pd-worktrees/wave2`" | assumption · blocker | How do you know worktree runs import the worktree's code? | RESOLVED | Inferred, not known. Step 3 opens with a probe: a planted `raise RuntimeError` in the worktree's `database.py` must turn the worktree suite red at import. |
| 6 | L353+L543 | "the irreversible wave" / "Code rollback is `git revert`" | inconsistency · blocker | Which is it, and does D1 stand? | RESOLVED | The code is revertible; mixed-window data isn't. "The irreversible wave" is inherited, wrong wording. D1 stands because C5b is design work (L349, L351) whose failures would be indistinguishable from a mechanical codemod's; the worktree reason (L350) is retired by C17a. |
| 7 | L395 | "a design decision, not a mechanical edit" | completeness · blocker | What is the decision, and who makes it? | RESOLVED | There isn't one; L395 is wrong. The parent is set through a separate `_safe_set_parent` call, so `:837` is the mechanical edit `entity_id=stem` → `display_id=stem`. |
| 8 | L441 | "decide per site whether the display-less fallback" | completeness · blocker | Who decides, by what criterion, at which step? | RESOLVED | Moot: F sites are UI tests that never reach `_read_entity_display`. Today the fallback is covered by accident (strict off); step 2 removes that, so step 2 adds one legacy-row test asserting the WARN and the fallback. F sites become ordinary registrations via rule 3 at step 1. |
| 9 | L507+L437 | "strict defaults on" / "id unchanged" | assumption · blocker | Between steps 2 and 3, what does strict mode do with `'bs-mixed'`? | RESOLVED | It raises, which would turn 36 of 42 C sites red at step 2. Step 1 rewrites those 36 to `{BRAINSTORM_FIXTURE_DATE}-{n:06d}-{slug}` via the repo-wide mapping; the other 6 stay byte-identical; all 42 take `display_id=` at step 3. L437/L443 are wrong as written. |
| 10 | doc | (no problem statement; D5 measures code shape) | completeness · blocker | What does Wave 2 solve, what happens without it, and what shows it's solved? | RESOLVED | It removes the four text parses, the `init_project_state` bypass (live: its projects break B8), the non-numeric brainstorm failure, and the untested production path. Solved when the inventory is 28 → 24, D5's grep is clean, and B8 stays at 0 after real registrations on the new build. |
| 11 | L453 | "Route it to category D" | inconsistency · minor | Where does `'000-v1'` belong? | RESOLVED | It stays category B. Categories describe what the walker sees; hand review is a codemod outcome. L453 is wrong. |
| 12 | L443 | "carrying no downstream risk" | reasoning · minor | How do you know no test reads the C display row lost at step 3? | RESOLVED | Not known. Readers go red at step 3 and are updated there. "No downstream risk" holds for A only. |
| 13 | L507 | "now-small attributable residue" | vagueness · minor | How small, and what if it isn't? | RESOLVED | Expected: the experiment's 14 non-format failures plus display-row expectations. Drill: any step-2 failure outside the 14 named in the step-0 baseline that isn't a display-row expectation stops the step. |
| 14 | L545 | "the cutover timestamp" | vagueness · minor | Recorded where, by whom? | RESOLVED | The merge commit's committer time, recorded in the plan by the operator when the gate closes. |
| 15 | L539 | "still needs its declared decision" | completeness · minor | At which step? | RESOLVED | Recorded at step 3, before C7's step 4. |
| 16 | L461+L464 | "from `database.py`, `hooks/lib/conftest.py:37`, `mcp/conftest.py:31`" | completeness · minor | The grep also matches `test_issue_spawn.py`'s fixture and conftest docstrings. Which list is the criterion? | OPEN | — (unasked) |
| 17 | L480 | "a pd MCP server has started on it" | vagueness · minor | Observed how? | OPEN | — (unasked) |
| 18 | L506 | "(A, B, F)" | ambiguity · minor | What does step 1 do to A sites, whose ids don't change? | OPEN | — (unasked) |
| 19 | L335 | "small but real" | vagueness · minor | Small by what measure? | OPEN | — (unasked) |

☑ 15 resolved · 4 open · 0 dismissed

**Revised 2026-09-23 by the stage review** — a subagent review of the step-0 stage summary, each checkable claim verified against the tree before it was absorbed:

- **L13** — step 2's stop rule keys on the list step 1's exit leaves, not the step-0 baseline's 14; 13 of those 14 are id-format fallout step 1 removes.
- **L3** — the mapping keys on (kind, literal), and seq stepping is scoped to files that register the literal.
- **L4** — the rewrite is narrowed to three positions plus a committed hand-review list; the gate allows only a reviewed allowlist.
- **L9** — `{BRAINSTORM_FIXTURE_DATE}` was never defined; the rule is written out as `20260101-{n:06d}-{slug}`.
- **L1** — step 3's call-shape codemod skips the 9 MCP-tool calls, which move with the tool surface at step 4. Steps 3–5 were then rearranged, add first and delete last: step 3's codemod moves test calls only, production callers move at step 4, and `entity_id`/`_strict_id_format` go at step 5.

## Wave 3 — census, allocator, guard

**C1 → C2 → C3**, with C3 also waiting on C6. C3's predicate is now `is_legacy`, and **B8** is what keeps its precondition true across Wave 2.

**Amended by Wave 2 / D3.** C3's guard refuses a bucket holding non-archived entities that lack display rows. After D3, brainstorms are display-less **by design**, so C3's predicate becomes `is_legacy = 1 OR kind IN NON_SEQUENCE_KINDS` — otherwise the guard refuses every brainstorm bucket permanently, the first time the new exemption is exercised. This is the same restatement sweep D3 applies to the doctor check; C3 restates the invariant one wave later. Checked at step 3: nothing allocates a brainstorm sequence, so a guard scoped to the allocating bucket never examines one; the exemption bites only if C3 counts entities beyond that bucket, and Wave 3 settles the scope.

**C1 and C2 SHIPPED 2026-09-22 (`e9f5774f`).**

## Wave 4 — readers and producers

Parallel once Wave 2 lands: **C8–C12**, **C13**, **C14**, **C15–C16**, **C17**, **C18**, **C19/C20b**.

**C17a — a git worktree resolves to its repository's workspace** (decision 6). **SHIPPED 2026-09-23 (`833095a9`).** `_repository_root()` maps a linked worktree to its main checkout before any path-keyed resolution, in both `resolve_workspace_uuid` and `resolve_startup_workspace_uuid`. A dry run over all 23 live workspace roots moved exactly the three worktrees, all to project_illium's workspace. Their rows were then retired (snapshot `entities.db.pre-c17a-20260923`; each row printed in full, so it can be re-inserted verbatim). The worktrees' own `.claude/pd/workspace.json` files are left in place: nothing reads them after C17a, and `illium-golive` is protected. Independent of Wave 2 — no schema change and no `register_entity` signature change. **Two readers were missed and fixed in `38935d59`** (stage review): the UI's startup board lookup (`ui/__init__.py`) and `cleanup_backlog.py`'s re-projection both keyed on the raw path, so from a worktree they missed the repository's workspace; both now go through `_repository_root` first, each with a real-git worktree test. `illium-golive`, the protected live-deploy worktree, now resolves to project_illium's workspace; its directory and `live-deploy` branch were not touched.

- **Contract.** `resolve_workspace_uuid` maps a worktree to the workspace of its `git rev-parse --git-common-dir`, not its root commit, which separate clones share. A working tree whose git directory lives in a bare repository (terry_agent: `/Users/terry_agent` → `~/projects/terry_agent-control/terry_agent.git`) is that repository's only workspace.
- **Scope.** Retire the three empty worktree **workspace rows** — `illium-golive`, `illium-live-debug`, `illium-architecture-re-build`, 0 entities each. Registry rows only; the directories stay, and `illium-golive` is protected. Correct `_compute_legacy_project_id`'s docstring (`project_identity.py:811`).
- **Verify, red-first.** From inside a worktree, allocation and registration land in the repository's workspace. Today the number comes from project_illium's counter and the row lands in the worktree's own workspace (`entity_server.py:597-624`).
- **Unblocks** C5b and C17: once `project_id` and `workspace_uuid` agree for worktrees, C5b goes back to plain alias removal.

**C12 shrinks by one site.** Its `type_id.split` inside `promote_entity` left with the method in `2d654e1a`.

Apply **correction 3b** (from B3b): C8 gains the orphan-row fixture; C11 gains `feature_lifecycle.py:97` and must preserve its realpath containment check.

## Wave 5 — recreate and gate

**C22** then **C21**.

Apply **correction 3**: re-derive the four pair groups at execution time. Neither this document's literals nor the parent's are complete, and the set drifts every time any workspace creates a project.

**C22's scope is decision 2: the 11 unarchived live rows, collapsing to 10** — 6 backlog + `P001` (absorbing `P001-openclaw-gap-analysis`), `P002`, `P003`, `P004-entity-db-redesign`. Add **C22a — `reparent_entity`** (decision 3) as a prerequisite: `EntityDatabase.reparent_entity(type_id, new_parent_uuid)`, uuid-to-uuid, event-emitting, tested in isolation. C22 calls it for the 25 children of recreated projects.

**Verify C22a red-first:** re-parent a child, assert the new `parent_uuid`, assert the old parent's child count dropped and the new parent's rose, and assert the self-reference trigger still rejects `parent_uuid = uuid`. Then assert `P004-entity-db-redesign`'s replacement holds 16 children and the archived original holds 0 — the assertion that fails if C22 skips the unpaired project, which its parent Verify cannot see.

**Why this is not optional — C22 as written orphans 79 children, and its Verify cannot see it.** Every child carries `parent_uuid` → a legacy row. C22 creates a *new* project with a *new* uuid; nothing re-parents:

| Legacy parent | Workspace | Children | `completed`, not archived |
|---|---|---|---|
| `P001` | cast-below | 29 | 9 |
| `P004-entity-db-redesign` | pedantic-drip | **16** | **16** |
| `P001` | terry_agent | 12 | 9 |
| `P002` / `P003` / `P001-agent-orchestrator` | mixed | 12 | 5 |
| 9 backlog + brainstorm parents | pedantic-drip | 10 | 1 |

After C22, this effort's own replacement project is an empty row with an empty directory while all 16 of its features — and `docs/projects/P004-entity-db-redesign/` — stay on the archived row. C22's Verify checks re-parenting only *"after the pair collapse"*, and `P004` is in no pair. Re-parenting 16 children by uuid is exactly the *"bespoke insert"* C22's Interface forbids.

**44 of the 79 are unreachable.** cast-below's 29 and terry_agent's 15 sit in repos where C22's "ordinary creation paths" — which run in the current project's context — cannot execute. cast-below's `project:P001` is `is_legacy=1, is_archived=0, completed, 29 children` and is invisible to C22 by construction.

---

---

## Sequencing

```
Part 1   B2 ──┐
         B3b ─┤   (independent; any order, one commit each)
         B7 ──┤
         B8 ──┘

Part 2   C23 ──────────────────────────────────┐
         C4 ── C5 ── C6 ─┬─ C7 ─── C22 ────────┤
                         ├─ C8–C12 ────────────┤
                         ├─ C13 ───────────────┤
                         ├─ C15–C16 ───────────┤
                         ├─ C18 ───────────────┼── C21
                         └─ C3 ────────────────┤
         C1 ── C2 ─┬─ C3 (also needs C6) ──────┤
                   ├─ C14 ─────────────────────┤
                   ├─ C17 ─────────────────────┤
                   └─ C19 ── C20b ─────────────┘

         C17a ✓ (worktree → repository's workspace, 833095a9) ── C5b (project_id / parent_type_id removal), C17
         (C5b ships after Wave 2)
```

**C5b is new (Wave 2 re-plan, D1).** It is deliberately *not* a Wave 2 predecessor: it removes the two deprecated aliases, involves no schema change, and is revertible, so it ships after the cutover rather than inside it. **C17a is new (decision 6)** and precedes both C5b and C17; it does not depend on Wave 2.

B8 is not a formal predecessor of C3 — C3 would compile without it — but shipping C3 without B8 means its live precondition degrades unobserved from the day B6 ran. Treat it as one.

---

## Gates

Every task re-runs all four. **`plugins/pd/scripts/` is outside the standard suite scope**, which is how a live archival regression shipped unnoticed: `cleanup_backlog.py` kept writing `status='archived'` after the reader moved to the `is_archived` flag, and no gate covered it. Any task touching that directory — B7 touches four files in it — must run its tests explicitly. **Only two gates run in CI** — `.github/workflows/ci.yml` invokes `./validate.sh` and `test-hooks.sh` and nothing else, so the full suite and the audit are local-only. A task that ships green on CI has had its two weakest gates checked. Baseline **re-derived 2026-09-23** — the three pytest figures at `38935d59`, after C4/C23/C1/C2, `2d654e1a` and C17a (the 3902 figure this plan was written with predates them; a 4024 figure recorded mid-session was never reproducible, and is not the step-0 manifest's 4,024, which counts all four scopes in one process):

```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q   # 3975 passed / 3 skipped  (the standard 3-path scope every recorded pd figure uses)
plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests -q                                  # 49 passed             (OUTSIDE the 3-path scope — see note)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q         # scripts + audit together: 56 passed
./validate.sh                                                                                       # 0 / 0
bash plugins/pd/hooks/tests/test-hooks.sh                                                                                 # 66/66 passed, 1 skipped
```

Snapshot before any task that writes to the live registry — WAL mode means `.backup`, never `cp`:

```bash
sqlite3 ~/.claude/pd/entities/entities.db ".backup '$HOME/.claude/pd/entities/entities.db.pre-<task>-$(date +%Y%m%d)'"
sqlite3 'file:<snapshot>?mode=ro&immutable=1' "PRAGMA integrity_check; SELECT COUNT(*) FROM entities;"   # a bare path opens it read-write
```

---

## Risks

- **The registry is shared and live.** 24 workspaces write to one file. Every literal in this document is a measurement with a timestamp, not a constant. Re-derive at execution; assert shapes and invariants, not counts.
- **~~Wave 2 is the only irreversible step.~~ Corrected 2026-09-22 (Wave 2 re-plan).** Checked: `V2_MIGRATIONS` ends at 7, `V2_SCHEMA_VERSION = 7`, and entry 7 is B8's trigger — already shipped. C5/C6/C7 are signature and call-site changes that **add no migration and write nothing to the live registry**, so the code rollback is `git revert`. What is genuinely irreversible is data written by an *old build during the mixed-version window*, which is what the stop-the-world gate closes. There is still no `V2_MIGRATIONS_DOWN`, so this reasoning must be re-checked for any later wave that does add one.
- **`.backup` is not a rollback, and Gates prescribes it anyway.** One file, seven workspaces with entities. A restore reverts ~153 rows in six uninvolved repos and resets `feature next_val` below numbers already materialised as directories and branches — feature counters as of 2026-09-23: 135 pedantic-drip, 115 project_illium, 80 fractorg, 51 terry_agent, 22 cast-below. Nothing in code compares `sequences.next_val` to what is on disk; only `/pd:create-feature`'s prose hard stop does, and on 2026-09-23 it would have fired — see *Counter drift* below. **Closed 2026-09-22** — see *Rollback* at the end of Wave 2: detect via `check_display_row_invariant`, remediate only rows created after the cutover timestamp, never restore the file wholesale. Note also that `~/.claude/pd/entities/` already holds `.db.pre-*` snapshots with `-shm`/`-wal` siblings — made with `cp`, which Gates forbids — and restoring one of those is a torn read on top of all the above.
- **The gap between now and C6 keeps producing display-less rows — through `init_project_state` only.** Production otherwise registers strictly (env unset → `strict = True`), so every other registration already writes a display row (calvin L10). B8 makes the remaining source visible; it does not stop it. Only C5/C6 stop it.
- **The suite has never exercised the display-row write.** Both conftests default `PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0`, so the `if strict:` branch at `database.py:7708` is reached only by the 13 tests of `mcp/test_issue_spawn.py`, via a module-scope autouse fixture at `:54`. Forcing the flag on today fails 751 of them. C5 makes that branch unconditional, which is why D5 makes *deleting* the flag the exit criterion.
- **Counter drift, found 2026-09-23.** A read-only scan of all 24 workspaces found project_illium's feature counter at 57 with directories up to 114, and terry_agent's at 36 with directories up to 50; both would have hard-stopped `/pd:create-feature`. Raised to 115 and 51 (snapshot `entities.db.pre-counterfix-20260923`), written with plain `sqlite3` so the live file stayed at schema 6 rather than being migrated as a side effect. Behind it are **152 feature directories the registry has never seen** (project_illium 78, fractorg 57, terry_agent 16, pedantic-drip 1). project_illium's 53 numbered 057–114 are in no snapshot back to May and have no event: pd stopped recording that repository's features in June 2026, the weeks its worktrees appeared. The census cannot protect numbers it cannot see, so C19/C20 (seed from disk) is the systematic fix, and C17a stops worktrees issuing numbers outside their repository's sequence.
- **Reviewer claims are not self-verifying.** Verify any claim about a symbol against `file:line` before absorbing it here.

---

## Out of scope

- The 22 historical duplicate feature numbers. Inert; repair would rename live directories and branches.
- The vestigial date-valued `brainstorm` counters (`next_val = 20260711` and four siblings). No creation path allocates from them; brainstorm identity is a timestamp. Leave them; do not "repair" them toward a real date.
- The v2 `sequences` shape divergence (RCA S8) — no live importer.
- Renaming existing `P00N-*` directories on disk. They belong to entities the clean break marked legacy; nothing renames them.
