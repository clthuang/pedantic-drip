# Structural Identity — Completion Plan

**Parent plan:** [2026-09-20-display-id-ownership-implementation.md](./2026-09-20-display-id-ownership-implementation.md) — the Contract/Interface/Verify text for **C1–C23** lives there and is **not restated here**. This document sequences what is left, records the corrections found while scoping it, and closes the one question the parent plan left open.
**Design:** [2026-09-20-display-id-ownership-design.md](./2026-09-20-display-id-ownership-design.md) (rev 3)
**RCA:** [../rca/20260920-display-id-ownership.md](../rca/20260920-display-id-ownership.md)
**Related, shipped:** [2026-09-22-soft-delete-design-and-plan.md](./2026-09-22-soft-delete-design-and-plan.md) (#081, `76c4a4cc`)

**Before executing any task below, run `calvin` on this document** (per `~/.claude/CLAUDE.md`). It carries no ledger yet.

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
| Python suite | 3902 passed / 3 skipped — **now 3970 / 3**, after C4/C23/C1/C2 and `2d654e1a` (six promotion tests removed) |
| `./validate.sh` | 0 errors / 0 warnings |
| Hook integration tests | 66/66 passed, 1 skipped |
| `register_entity`/`upsert_entity`/`register_entities_batch`/`_register_entity_no_display` call sites | **13 external production · 3 internal · 1,153 test** across 49 files (a 3-name census undercounts by 25) |
| Tests that fail once identity is mandatory (`STRICT_ID_FORMAT=1`) | **751** (707 failed + 44 errors) across 26 files — **693** `EntityIdFormatError`, 14 assertion-shaped (13 downstream of it, **1 a second class**) |
| Live `schema_version` vs build | file **6** · build `V2_SCHEMA_VERSION` **7** — migration 7 not yet applied live |
| Brainstorms | 100 · **97 carry display rows** (all non-legacy) · 3 without, all `is_legacy=1` |
| Workspaces with no `project_id_legacy` | **10 of 24** — 7 are deleted directories (4 stranded entities, a dead counter at 88); **3 are live worktrees of project_illium**, which `project_id` resolves to the **parent's** workspace (measured 2026-09-23) |
| Feature directories the registry has never seen | **152** — project_illium 78, fractorg 57, terry_agent 16, pedantic-drip 1 (read-only scan, 2026-09-23) |
| Feature counters behind their disk | project_illium 57 vs dirs to 114, terry_agent 36 vs 50 — **raised to 115 and 51 on 2026-09-23** (snapshot `entities.db.pre-counterfix-20260923`); the 3 illium worktrees' own buckets clear with C17a |

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

7. **Neither plan ever sized Wave 2's test surface.** The parent plan's *"roughly 15 production sites"* is accurate (16 measured). What no revision counted is **1,153 test call sites across 49 files** (a three-name census undercounts by 25 — `_register_entity_no_display` is a fourth), or the **751 tests** that fail the moment structured identity becomes mandatory, which itself cannot see those 25. Wave 2's cost is in the suite, not in production. Re-planned in full below.

8. **C5 removes two parameters too many.** `project_id` and `parent_type_id` appear nowhere in `_KNOWN_INFERENCE_SITES` and involve no schema change, so they split out as **C5b**. The justification is design risk, not edit count — 7 of 13 external production sites pass `project_id` with no `workspace_uuid`, and in git worktrees `project_id` resolves to the parent repository's workspace (decision 6, C17a). (Rev 1 of Wave 2 argued from an edit count of 1,072; that figure double-counted two overlapping sets — the union is 973, and 960 of those ride along on lines C5 already rewrites. Withdrawn.) See Wave 2 / D1.

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

### Measured 2026-09-23 — re-derive before execution

Call sites counted by AST walk over `plugins/pd/**/*.py` across **four** names — `register_entity`, `upsert_entity`, `register_entities_batch`, **and `_register_entity_no_display`**. Rev 1 counted three and was wrong by 25 sites.

| | Sites |
|---|---|
| Production, external callers | **13** |
| Production, internal delegations | 3 — `:7814` (inside **`_register_entity_no_display`**, a test-only helper living in production code), `:7874` (`upsert_entity`), `:10698` (`register_entities_batch`) |
| Test / conftest | **1,153** across 49 files |

| Parameter | External prod | Internal | Test |
|---|---|---|---|
| `entity_id` | 13 | **3** | 1,113 (150 keyword + 963 positional) |
| `project_id` | **13 — every one** | 2 | 973 |
| `parent_type_id` | **0** | 2 | 99 — **a subset of the 973, not additive** |
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

### D1 — C5 sheds two parameters, not four

`_KNOWN_INFERENCE_SITES` (`test_audit_writes.py:532`) attributes exactly four lines in `register_entity` to C6 — `database.py:7575` (regex) and `:7709/:7710/:7711` (slice). `project_id` and `parent_type_id` appear nowhere in it, and correctly so: they are SQL/uuid lookups, not text parses.

**Decision unchanged: C5 removes `entity_id` and `_strict_id_format` only.** `project_id` and `parent_type_id` defer to **C5b**.

**Rev 1's stated reason was wrong and is withdrawn.** It claimed the aliases carry "1,072 test-site edits on an orthogonal axis". Two errors: the two sets overlap (all 99 `parent_type_id` sites are among the 973 `project_id` sites, so the union is **973**, not 1,072), and **960 of those 973 — 98.7% — also supply `entity_id`**, landing on lines C5 already rewrites. Deferring does not avoid those edits; it re-opens them. On edit count alone, deferral is the more expensive option.

**The real reason to defer is design risk, not edit count:**

- **7 of 13 external production sites pass `project_id` with no `workspace_uuid`** — `backfill.py:443/:570/:617/:735/:837`, `entity_server.py:474`, `scripts/parse_backlog_md.py:262`. Each needs genuine re-homing design.
- **`project_id` resolves to the wrong workspace in git worktrees.** Rev 2 said it "cannot address 10 of 24 workspaces"; corrected 2026-09-23. Of the 10 with no `project_id_legacy`, 7 are deleted directories. The other 3 are live worktrees of project_illium, and `_compute_legacy_project_id` gives every one of them the repository's root-commit id, so each `project_id`-only write resolves to **project_illium's** workspace. Startup backfill (`entity_server.py:276`) would register a worktree's artifacts there, and MCP `register_entity` with `auto_id` (`entity_server.py:597-624`) takes the number from project_illium's counter but registers the row in the worktree's own workspace. Nothing is damaged yet — the three worktree workspaces are empty. Decision 6 settles which workspace is right; **C17a** implements it.
- **`project_id` is not only a workspace alias.** At `database.py:7635-7645` the explicit kwarg is *also* the `entity_created` phase-event label, falling back to `workspaces.project_id_legacy` only when absent. Dropping it changes event metadata on an append-only table. C5b's Verify must assert those labels are byte-unchanged at all 13 sites.

Design risk of that shape is exactly what does not belong in the irreversible wave. Edit count was never the argument.

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

Exactly one of `(seq, slug)` or `display_id`; both or neither raises.

- **`(seq, slug)`** — sequence kinds. `entity_id = render_display_id(entity_type, seq, slug)`. Display row written **unconditionally**.
- **`display_id`** — `NON_SEQUENCE_KINDS` only, stored verbatim, no display row (D3).

**Why `display_id` is not the alias C5 forbids.** The "No alias" clause exists to stop a *parsed* alias hiding in a `_migration_13_*`-named helper where the audit auto-approves it. `display_id` is never parsed and is rejected for every sequence kind.

**The `display_id` path has two callers, both filename-stem sourced** (rev 1 claimed one, from a single site it did not sweep):

| Site | Source |
|---|---|
| `entity_status.py:190` | `.prd.md` stem from the brainstorms directory scan |
| `backfill.py:837` (`_register_brainstorm`) | `_brainstorm_stem`, same shape |

`backfill.py:837` additionally carries `_derive_parent` → `_safe_set_parent` handling, so it is a design decision, not a mechanical edit.

`entity_type` keeps its name — `kind` equals the old `entity_type` value and result dicts carry both as aliases, so renaming would churn 1,153 sites for nothing.

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

**The SQL change re-introduces the column that caused a vacuous green, and must not repeat it.** `checks.py:600-606` records it verbatim: the first version selected `e.kind`, older files raised, the `except` swallowed it, and the check reported green having never run. The existing `cols = PRAGMA table_info(entities)` probe at `:607` handles that — but its documented reading ("a file predating the column has no exempt rows") is **correct for `is_legacy` and wrong for `kind`**: a pre-migration-12 file still holds brainstorms, under `entity_type`. **Interface:** probe for `kind`, fall back to `entity_type` when absent, and never silently drop the clause.

**The only fixture that runs this check cannot reach the new branch.** `_make_db` (`test_checks.py:20`) stamps `schema_version = 9` and its `entities` table has `entity_type TEXT NOT NULL` and **no `kind` column**; `_entity()` (`:2233`) hardcodes `entity_type='feature'` and takes no kind parameter. Both need extending, or the exemption ships with zero coverage. Two red-first tests: brainstorm-without-display passes; feature-without-display still fails.

**The kind exemption is not the `is_legacy`-class hatch.** Since `2d654e1a` nothing at runtime writes `kind`: `promote_entity` was the only writer. The `enforce_immutable_entity_type`/`_type_id` triggers are still absent (dropped at migration 12; `test_database.py:948`/`:2604` pin that), but the `entities` CHECK pairs `type` with `kind` (`type='brainstorm' AND kind='brainstorm'` / `type='work' AND kind IN (…)`), so every single-column route into `NON_SEQUENCE_KINDS` is blocked — verified on a scratch copy of the live DDL, never the live file. Muting a row would take deliberate two-column SQL (`SET type='brainstorm', kind='brainstorm'`), which nothing in the codebase does. **Add one red-first test** asserting a single-column re-kind into `NON_SEQUENCE_KINDS` raises `IntegrityError`. With no runtime writer left, a `type`/`kind` immutability trigger is now possible — Wave 3, because it is a migration and Wave 2 deliberately has none.

**The 97 existing brainstorm display rows stay.** Measured live: 100 brainstorms, **97** with display rows, all non-legacy; the 3 without are all `is_legacy=1`; 0 violations today. Rev 1 said 96. They hold migration-13 parse-accident values (`20260221-012305-slug` → `seq=20260221`), and `_read_entity_display` (`workflow_state_server.py:371`) **prefers** a present row, so deleting them would flip 97 entities onto its stderr-WARN fallback. Doing nothing is both lazy and safe.

**Stated cost of doing nothing:** `_census_max(kind='brainstorm')` is frozen at seq **20260710** permanently. Inert — nothing allocates brainstorm sequences — but recorded rather than discovered later.

**Row-level exemption was considered and rejected:** `entity_display.seq` is `INTEGER NOT NULL`, so a NULL-seq marker needs a migration and would break this wave's "no migration" rollback property.

### D4 — the test migration is a codemod with a repo-wide completeness gate

| | Category | Sites | Treatment |
|---|---|---|---|
| **A** | round-trips exactly through `render_display_id` | **298** | Pure codemod; id unchanged. |
| **C** | non-sequence kind (brainstorm) | **42** | `display_id=` verbatim; id unchanged. |
| **B** | id must change | **675** | Codemod + reference sweep. |
| **D** | dynamic (f-string / variable / expr) | **98** | Hand review. |
| **E** | no `entity_id` argument | **15** | Inspect. |
| **F** | **via `_register_entity_no_display`** | **25** | **New in rev 2.** All in `ui/tests/test_entities.py`; 25 distinct ids, **0 conformant**, 92 in-file references. C6 deletes the helper, so these become ordinary registrations — decide per site whether the display-less fallback in `workflow_state_server.py:371` keeps a fixture or loses its only coverage. |

Total **1,153**. A + C = 340 byte-identical rewrites carrying no downstream risk.

**Rule 3 dominates and rev 1 left it undefined.** Of the literal-id sites, **665 have no leading digit** — `P001`, `bs-mixed`, `''` — so the "per-file counter + slug from the old text" rule is the majority case, not the footnote rev 1's table implied. It must specify counter seed, slug derivation, and collision policy against ids already present in the file. A per-file counter is also **not deterministic across files**, which the word "deterministic" in rev 1 wrongly implied.

| Old shape | Example | New | Precondition |
|---|---|---|---|
| `^(\d+)-(.+)$` | `1-a`, `00010-existing` | `001-a`, `010-existing` | **`seq >= 1`** |
| `^(\d+)$` | `00042` | `042-<stable token>` | `seq >= 1` |
| no leading digits (**majority, 665**) | `P001`, `bs-mixed`, `''` | per-file counter + slug from old text | — |

**`seq >= 1` is load-bearing:** `test_database.py:9317` registers `backlog` with `'000-v1'`. Rule 1 maps it to itself, but `render_display_id('backlog', 0, 'v1')` raises `seq must be a positive int` (`id_generator.py:85`). Route it to category D; a per-file gate would pass it silently because the literal never changed.

**The completeness gate is repo-wide, not per-file.** 86.0% of literal ids are referenced elsewhere in their own file (872 of 1,014 non-empty literals; the 1,015th is the empty string `''`, which no sweep can key on and which therefore goes to hand review), **and 33 distinct literals are registered in two or more files** — `'001-test'` in four, `'f1'` in four, `'child'` in three, `'P001'` in `test_database.py` + `test_frontmatter_sync.py`. A per-file gate cannot see those, and a per-file counter would hand the same literal two different new ids. After all files are rewritten, assert zero occurrences of each old literal **across the whole `plugins/pd` tree**, and pre-compute the 33 so the executor decides per id whether the two uses are independent fixtures or one contract.

**Substring hazard:** `'1-a'` is a substring of `'1-alpha'`; category F adds `'lim'`, `'older'`, `'newer'`. Replace string **constants** and `f"{kind}:{id}"` composites **via AST**, never `str.replace` over file text.

### D5 — the exit criterion that cannot be faked

Wave 2 is done when the strict flag is **deleted** — from `database.py`, `hooks/lib/conftest.py:37`, `mcp/conftest.py:31` — *and* `_register_entity_no_display` is gone, and the suite is green.

```bash
rg -l 'PD_REGISTER_ENTITY_STRICT_ID_FORMAT|_strict_id_format|_register_entity_no_display' plugins/pd
test $? -eq 1   # exit 1 = no matches = clean
```

Rev 1 wrote `rg -c … # expect 0`. `rg -c` prints per-file counts and prints **nothing** on a clean tree, exiting 1 — it never emits `0`, so the stated expectation could not be checked. Note `rg` honours `.gitignore`, which correctly skips `plugins/pd/.venv`.

After C6 there is no flag to set, so a green suite with the flag absent is green on the production path by construction. Today that path is reached by **all 13 tests in `mcp/test_issue_spawn.py`** — `:63` sits inside a module-scope `@pytest.fixture(autouse=True)` declared at `:54`, so it applies to the whole file. There is exactly one opt-in *site* repo-wide, which is not the same as one test; rev 1 conflated them. No test passes `_strict_id_format=True`; all 7 explicit sites pass `False`, and 25 more take `False` via the helper.

### ⛔ STOP-THE-WORLD GATE — it guards the merge, not the first commit

Wave 2 is built on a feature branch against temp databases; branch commits touch no live state. The hazard is a process on the **old build** writing display-less rows once the new build is in place.

**1. Cue the operator.** Person-in-the-loop by design (decision 4).

**2. Verify, do not assume:**

```bash
ps -axww | grep -i "entity_server\|workflow_state_server" | grep -v grep   # expect no output
lsof ~/.claude/pd/entities/entities.db                                      # expect no output
```

`lsof` alone is insufficient — servers connect on demand. **Verified 2026-09-22 21:31: 0 processes, 0 file holders.** The executing session cannot stop itself; stated exception.

**3. Snapshot after the world is stopped.** `.backup`, never `cp`; verify it **read-only** (`file:…?mode=ro`). Opening a snapshot read-write is what left `-shm`/`-wal` siblings beside six existing ones.

**4. Restart normally.** Live file is `schema_version 6`, build is `V2_SCHEMA_VERSION = 7`; the first process to open applies migration 7 (B8's trigger), which has not yet run live.

### Build order — never red

Rev 1 ordered the work C5 → C7 → codemod → C6 and accepted ~751 red tests across three steps. **That red window was never necessary.** The strict gate at `database.py:7575` only *rejects* non-conformant ids — conformant ones already pass today — and no display row is written either way while `strict` is false (`:7708`). So the id migration is independently shippable **green, right now**, before any signature change. Rev 1's "red is expected and is the point of using a branch" was an assertion, not a justification.

Each step below diffs against a green predecessor, so every failure is attributable to the step that caused it.

| # | Step | Gate |
|---|---|---|
| **0** | Commit the census walker (`scripts/census_register_sites.py`) with the four headline counts as its self-check. Capture the **node-id manifest** for all gate scopes. | green, unchanged |
| **1** | Codemod ids to conformant form (A, B, F) + repo-wide reference sweep. **No signature change.** | green |
| **2** | Delete both conftest `setdefault`s so strict defaults on; fix the now-small attributable residue. | green |
| **3** | **C5** — signature, unconditional display write, **D3's restated invariant + its eight sweep targets + the fixture extension**. | green |
| **4** | **C7-prod** — 13 external sites + the 3 upstream contracts. | green |
| **5** | **C6** — delete the 4 inference lines, the strict flag, and `_register_entity_no_display`. | green |
| **6** | Gates + D5's grep + manifest comparison. | green |

**The node-id manifest is not optional, and it is the one place the Risks section's "assert shapes, not counts" is suspended.** After a machine rewrite of 675+ call sites, "suite green" is satisfiable by a suite that tests strictly less — a codemod that deletes, renames, or collapses a test passes step 6 exactly as well as a correct one. At step 6 assert `passed_after ⊇ passed_before` **by node id**, and `collected_after == collected_before` modulo an enumerated delta with a one-line reason per entry. These are counts diffed against a manifest taken on the same tree, not measurements of the shared live registry, which is what that Risks rule actually governs.

**`_KNOWN_INFERENCE_SITES` needs an explicit rebase step, twice.** It is an EXACT-SET lint on `(path, lineno, idiom)` (`test_audit_writes.py:573`) — it fails on any line shift, not only on added or removed sites. Steps 3 and 4 shift `workflow_state_server.py:485/:707/:1147/:1429` and `backfill.py:756`. Step 5 must additionally strike the four C6 tuples and **lower `_INVENTORY_HIGH_WATER` from 28 to 24** (`:626`), whose comment says it moves down when a site is removed and never back up. Run `pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q` after **each** of steps 3, 4 and 5 — the same rebase was already required for C23 and again for C1/C2 in this campaign.

**Every step's gate includes `plugins/pd/scripts/tests`.** Six family call sites live under `plugins/pd/scripts` — `parse_backlog_md.py:262` plus 5 test sites — and that directory is outside the 3-path suite the Gates section flags as historically missed. A codemod regression there would otherwise surface only at step 6.

C7's three upstream contracts, unchanged from the parent plan:
- `generate_entity_id()` (`id_generator.py:92`) returns a string and discards `seq`/`slug`. It must return both.
- **Two** MCP tool surfaces expose `entity_id`, not one: `register_entity` (`entity_server.py:515`, param at `:517`) and `create_key_result` (`:1419`, param at `:1424`). Both become `seq`/`slug`. Rev 1 cited `:475`, which is a `db.register_entity(...)` **call site** inside `_process_create_key_result` (`:449`) — correct in the C7 drift table, wrong as a tool surface, and it hid the second tool entirely.
- `upsert_entity`'s **conflict lookup** (`WHERE workspace_uuid = ? AND type_id = ?`) moves to structured identity without breaking three-branch insert-or-update semantics.

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

**`plugins/pd/scripts/` still needs its declared decision** (into `_INFERENCE_SCAN_ROOTS`, or explicitly uncovered). `parse_backlog_md.py:262` is a caller the lint will never name.

### Rollback — Wave 2 adds no migration

`V2_MIGRATIONS` ends at **7**, `V2_SCHEMA_VERSION = 7`, and entry 7 is B8's trigger, already shipped. C5/C6/C7 are signature and call-site changes that **add no migration and write nothing to the live registry**. Code rollback is `git revert`.

The residual risk is data written by an **old build during the mixed-version window** — what the stop-the-world gate closes. Those rows are identifiable by the existing detector: non-legacy, non-exempt entities with no display row. Remediate only rows created after the cutover timestamp.

**Do not restore the snapshot wholesale.** One file holds seven workspaces' entities; a full restore reverts ~153 rows in six uninvolved repos and resets `sequences.next_val` below numbers already materialised as directories and branches — feature counters as of 2026-09-23: 135 pedantic-drip, 115 project_illium, 80 fractorg, 51 terry_agent, 22 cast-below. project_illium's and terry_agent's were raised that day to clear drift, so restoring any earlier snapshot puts both back behind their disk. `/pd:create-feature` hard-stops on that (step 2 of the command); a path without that prose guard would re-mint a number that already owns a directory — the RCA's opening incident. The snapshot is forensic evidence, not a rollback plan.

### Found during review, deliberately out of scope

Both pre-existing, neither caused by Wave 2, neither blocking it:

- ~~**`promote_entity` is type-locked.**~~ **Resolved 2026-09-23 — deleted in `2d654e1a` (decision 5).** The framing here was wrong: its spec allowed only kind changes the `type`/`kind` CHECK permits, and its designed use, backlog → feature, worked. The defect was that it had never been called.
- **`_compute_legacy_project_id`'s docstring is false** (`project_identity.py:811`). It says migration-only, but it is `project_id`'s live source in both MCP servers (`entity_server.py:235`, `workflow_state_server.py:237`) and in `reconciliation_orchestrator/__main__.py:104` and `task_promotion.py:354`. What it hid is D1's worktree misrouting. **Moved into C17a (decision 6)**, which fixes both.

## Wave 3 — census, allocator, guard

**C1 → C2 → C3**, with C3 also waiting on C6. C3's predicate is now `is_legacy`, and **B8** is what keeps its precondition true across Wave 2.

**Amended by Wave 2 / D3.** C3's guard refuses a bucket holding non-archived entities that lack display rows. After D3, brainstorms are display-less **by design**, so C3's predicate becomes `is_legacy = 1 OR kind IN NON_SEQUENCE_KINDS` — otherwise the guard refuses every brainstorm bucket permanently, the first time the new exemption is exercised. This is the same restatement sweep D3 applies to the doctor check; C3 restates the invariant one wave later.

**C1 and C2 SHIPPED 2026-09-22 (`e9f5774f`).**

## Wave 4 — readers and producers

Parallel once Wave 2 lands: **C8–C12**, **C13**, **C14**, **C15–C16**, **C17**, **C18**, **C19/C20b**.

**C17a — a git worktree resolves to its repository's workspace** (decision 6). Independent of Wave 2 — no schema change and no `register_entity` signature change — so it can land before it, and should land before any pd session runs in a project_illium worktree.

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

         C17a (worktree → repository's workspace) ── C5b (project_id / parent_type_id removal), C17
         (C17a has no Wave 2 dependency; C5b ships after Wave 2)
```

**C5b is new (Wave 2 re-plan, D1).** It is deliberately *not* a Wave 2 predecessor: it removes the two deprecated aliases, involves no schema change, and is revertible, so it ships after the cutover rather than inside it. **C17a is new (decision 6)** and precedes both C5b and C17; it does not depend on Wave 2.

B8 is not a formal predecessor of C3 — C3 would compile without it — but shipping C3 without B8 means its live precondition degrades unobserved from the day B6 ran. Treat it as one.

---

## Gates

Every task re-runs all four. **`plugins/pd/scripts/` is outside the standard suite scope**, which is how a live archival regression shipped unnoticed: `cleanup_backlog.py` kept writing `status='archived'` after the reader moved to the `is_archived` flag, and no gate covered it. Any task touching that directory — B7 touches four files in it — must run its tests explicitly. **Only two gates run in CI** — `.github/workflows/ci.yml` invokes `./validate.sh` and `test-hooks.sh` and nothing else, so the full suite and the audit are local-only. A task that ships green on CI has had its two weakest gates checked. Baseline **re-derived 2026-09-23**, after C4/C23/C1/C2 and `2d654e1a` (the 3902 figure this plan was written with predates them; a 4024 figure recorded mid-session was never reproducible):

```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q   # 3970 passed / 3 skipped  (the standard 3-path scope every recorded pd figure uses)
plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests -q                                  # 48 passed             (OUTSIDE the 3-path scope — see note)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q         # scripts + audit together: 55 passed
./validate.sh                                                                                       # 0 / 0
bash plugins/pd/hooks/tests/test-hooks.sh                                                                                 # 66/66 passed, 1 skipped
```

Snapshot before any task that writes to the live registry — WAL mode means `.backup`, never `cp`:

```bash
sqlite3 ~/.claude/pd/entities/entities.db ".backup '$HOME/.claude/pd/entities/entities.db.pre-<task>-$(date +%Y%m%d)'"
sqlite3 <snapshot> "PRAGMA integrity_check; SELECT COUNT(*) FROM entities;"
```

---

## Risks

- **The registry is shared and live.** 24 workspaces write to one file. Every literal in this document is a measurement with a timestamp, not a constant. Re-derive at execution; assert shapes and invariants, not counts.
- **~~Wave 2 is the only irreversible step.~~ Corrected 2026-09-22 (Wave 2 re-plan).** Checked: `V2_MIGRATIONS` ends at 7, `V2_SCHEMA_VERSION = 7`, and entry 7 is B8's trigger — already shipped. C5/C6/C7 are signature and call-site changes that **add no migration and write nothing to the live registry**, so the code rollback is `git revert`. What is genuinely irreversible is data written by an *old build during the mixed-version window*, which is what the stop-the-world gate closes. There is still no `V2_MIGRATIONS_DOWN`, so this reasoning must be re-checked for any later wave that does add one.
- **`.backup` is not a rollback, and Gates prescribes it anyway.** One file, seven workspaces with entities. A restore reverts ~153 rows in six uninvolved repos and resets `feature next_val` below numbers already materialised as directories and branches — feature counters as of 2026-09-23: 135 pedantic-drip, 115 project_illium, 80 fractorg, 51 terry_agent, 22 cast-below. Nothing in code compares `sequences.next_val` to what is on disk; only `/pd:create-feature`'s prose hard stop does, and on 2026-09-23 it would have fired — see *Counter drift* below. **Closed 2026-09-22** — see *Rollback* at the end of Wave 2: detect via `check_display_row_invariant`, remediate only rows created after the cutover timestamp, never restore the file wholesale. Note also that `~/.claude/pd/entities/` already holds `.db.pre-*` snapshots with `-shm`/`-wal` siblings — made with `cp`, which Gates forbids — and restoring one of those is a torn read on top of all the above.
- **The gap between now and C6 keeps producing display-less rows.** B8 makes that visible; it does not stop it. Only C5/C6 stop it.
- **The suite has never exercised the display-row write.** Both conftests default `PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0`, so the `if strict:` branch at `database.py:7708` is reached only by the 13 tests of `mcp/test_issue_spawn.py`, via a module-scope autouse fixture at `:54`. Forcing the flag on today fails 751 of them. C5 makes that branch unconditional, which is why D5 makes *deleting* the flag the exit criterion.
- **Counter drift, found 2026-09-23.** A read-only scan of all 24 workspaces found project_illium's feature counter at 57 with directories up to 114, and terry_agent's at 36 with directories up to 50; both would have hard-stopped `/pd:create-feature`. Raised to 115 and 51 (snapshot `entities.db.pre-counterfix-20260923`), written with plain `sqlite3` so the live file stayed at schema 6 rather than being migrated as a side effect. Behind it are **152 feature directories the registry has never seen** (project_illium 78, fractorg 57, terry_agent 16, pedantic-drip 1). project_illium's 53 numbered 057–114 are in no snapshot back to May and have no event: pd stopped recording that repository's features in June 2026, the weeks its worktrees appeared. The census cannot protect numbers it cannot see, so C19/C20 (seed from disk) is the systematic fix, and C17a stops worktrees issuing numbers outside their repository's sequence.
- **Reviewer claims are not self-verifying.** Verify any claim about a symbol against `file:line` before absorbing it here.

---

## Out of scope

- The 22 historical duplicate feature numbers. Inert; repair would rename live directories and branches.
- The vestigial date-valued `brainstorm` counters (`next_val = 20260711` and four siblings). No creation path allocates from them; brainstorm identity is a timestamp. Leave them; do not "repair" them toward a real date.
- The v2 `sequences` shape divergence (RCA S8) — no live importer.
- Renaming existing `P00N-*` directories on disk. They belong to entities the clean break marked legacy; nothing renames them.
