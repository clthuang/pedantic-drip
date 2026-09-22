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
| Identity-inference sites detected | 28 (6 sanctioned, 22 to remove) |
| Python suite | 3902 passed / 3 skipped |
| `./validate.sh` | 0 errors / 0 warnings |
| Hook integration tests | 66/66 passed, 1 skipped |

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

   `select_legacy_entities` keys on `is_legacy = 1` (`clean_break.py:110`) and returns 180 unconditionally, forever. It is a **selector of the legacy set**, not a worklist that drains — the "returns 0 after" framing only ever made sense under the tag model. C3's gate as written can never go green. **B8 is its replacement.**

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

**Why it must land before C3.** C3's guard refuses allocation when a bucket holds non-legacy entities lacking display rows. Between now and C6, `init_project_state` still passes `_strict_id_format=False` (`feature_lifecycle.py:321`) and `register_entity` writes the display row only `if strict:` (`database.py:7637`) — so **every project created in any of the 24 workspaces adds a fresh violation**. C3 then refuses that bucket forever. B8 turns a silent accumulation into a failing check the moment it starts. It also replaces parent C3's live-precondition gate, which is unsatisfiable as written (see Correction 2).

**Verify.** Green on the live registry (0 rows — confirmed today). Insert a non-legacy entity with no display row into a fixture; assert the check fails and names that uuid. Then assert that `UPDATE entities SET is_legacy = 1` on that row **raises**, rather than turning the check green — that assertion is the whole point of part (b).

**Non-vacuity gate.** A `try/except` around a missing `entity_display` table makes the hermetic 0/0 test pass on the legacy-schema fixture while the check never runs. The fixture must contain the table, and one test must observe the check in its **failing** state.

**Depends.** Nothing. Ship early; it measures the drift the rest of the plan has to live with.

---

# Part 2 — Release C, the cutover

Task definitions are in the parent plan. This section only sequences them and marks where the corrections above apply. Nothing in Part 2 has started.

## Wave 1 — version guard for the next cutover

**C23.** No dependencies; ships first. An old MCP server holding the shared plugin cannot write to a post-cutover file. Without it, `_migrate_v2` loops zero times on a file newer than the build (`database.py:10850`) and writes anyway — the only `V2_SCHEMA_VERSION` reference on the write path is the import-time `assert max(V2_MIGRATIONS) == _V2_SCHEMA_VERSION` at `:6406`, which compares the build to itself.

**C23 cannot protect its own cutover.** The assertion lives in `EntityDatabase.__init__` of the build that also performs the version bump, so it is absent from every process that predates it. That is not a defect to fix here — it is inherent to a read-side guard shipping alongside the write it guards.

**This cutover is protected operationally instead (decision 4):** a hard stop-the-world before Wave 2, cued to the operator, verified with `ps` and `lsof`. See the gate at the top of Wave 2. C23 ships in Wave 2 as written and guards the *next* version bump, when every running process will already carry it.

## Wave 2 — the locked core

> ### ⛔ STOP-THE-WORLD GATE — run before the first Wave 2 commit lands
>
> Wave 2 changes `register_entity`'s signature and deletes the registration parsers. A process on the old build keeps calling `register_entity(entity_id=…, _strict_id_format=False)` and mints display-less rows into whichever of the 24 workspaces it is serving. `run_backfill` fires at every MCP start and swallows failures to stderr, which MCP does not surface — so **nothing reports this while it happens**.
>
> **1. Cue the operator.** Wave 2 does not begin until every other Claude Code instance is stopped. This is a person-in-the-loop step by design (decision 4); do not proceed on the assumption it happened.
>
> **2. Verify, do not assume:**
>
> ```bash
> ps -axww | grep -i "entity_server\|workflow_state_server" | grep -v grep   # expect no output
> lsof ~/.claude/pd/entities/entities.db                                      # expect no output
> ```
>
> `lsof` alone is insufficient — MCP servers connect on demand, so a live server shows in `ps` while holding no file handle. At the time this plan was written: **0 file holders, 2 live server processes.** Check both.
>
> **3. Snapshot after the world is stopped, not before** — a snapshot taken while a writer is live is a torn read of the very state you are protecting.
>
> **4. Restart normally afterwards.** The first process to start on the new build performs the migration; the rest see the bumped version.

**C4 → C5 → C6 → C7.** The parent plan's largest unit; C5 and C7 land together. This is where the `P` prefix is dropped (decided 2026-09-21) and where `register_entity` starts taking `seq`/`slug` as data.

Apply **correction 4**: C7's site enumeration must add `entity_status.py:190` and `plugins/pd/scripts/parse_backlog_md.py:254`, and `plugins/pd/scripts/` needs a decision — either bring it into the scan roots or state explicitly that it is a utility directory the lint does not cover. Leaving it undeclared is how a parser survives the cutover. Note B7 already has to touch four files in that directory, so the decision lands before Wave 2 either way.

## Wave 3 — census, allocator, guard

**C1 → C2 → C3**, with C3 also waiting on C6. C3's predicate is now `is_legacy`, and **B8** is what keeps its precondition true across Wave 2.

## Wave 4 — readers and producers

Parallel once Wave 2 lands: **C8–C12**, **C13**, **C14**, **C15–C16**, **C17**, **C18**, **C19/C20b**.

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
```

B8 is not a formal predecessor of C3 — C3 would compile without it — but shipping C3 without B8 means its live precondition degrades unobserved from the day B6 ran. Treat it as one.

---

## Gates

Every task re-runs all four. **`plugins/pd/scripts/` is outside the standard suite scope**, which is how a live archival regression shipped unnoticed: `cleanup_backlog.py` kept writing `status='archived'` after the reader moved to the `is_archived` flag, and no gate covered it. Any task touching that directory — B7 touches four files in it — must run its tests explicitly. **Only two gates run in CI** — `.github/workflows/ci.yml` invokes `./validate.sh` and `test-hooks.sh` and nothing else, so the 3902-test suite and the audit are local-only. A task that ships green on CI has had its two weakest gates checked. Baseline as of 2026-09-22:

```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q   # 3902 passed / 3 skipped  (the standard 3-path scope every recorded pd figure uses)
plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests -q                                  # 30 passed             (OUTSIDE the 3-path scope — see note)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q
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
- **Wave 2 is the only irreversible step.** There is no `V2_MIGRATIONS_DOWN`. Reversal is a forward compensating write, and the event log keeps both sides forever. Rehearse on a `.backup` copy.
- **`.backup` is not a rollback, and Gates prescribes it anyway.** One file, seven workspaces with entities. A restore reverts ~153 rows in six uninvolved repos and resets `feature next_val` below numbers already materialised as directories and branches — 135 pedantic-drip, 88 illium-regime, 80 fractorg, 57 project_illium, 36 terry_agent, 22 cast-below. The next `/pd:create-feature` in any of them re-mints a number that already owns a `docs/features/NNN-*` directory and a branch: the RCA's opening incident, in four repos at once. Nothing compares `sequences.next_val` to what is on disk. **This plan has no restore procedure; it needs one before Wave 2.** Note also that `~/.claude/pd/entities/` already holds `.db.pre-*` snapshots with `-shm`/`-wal` siblings — made with `cp`, which Gates forbids — and restoring one of those is a torn read on top of all the above.
- **The gap between now and C6 keeps producing display-less rows.** B8 makes that visible; it does not stop it. Only C5/C6 stop it.
- **Reviewer claims are not self-verifying.** Verify any claim about a symbol against `file:line` before absorbing it here.

---

## Out of scope

- The 22 historical duplicate feature numbers. Inert; repair would rename live directories and branches.
- The vestigial date-valued `brainstorm` counters (`next_val = 20260711` and four siblings). No creation path allocates from them; brainstorm identity is a timestamp. Leave them; do not "repair" them toward a real date.
- The v2 `sequences` shape divergence (RCA S8) — no live importer.
- Renaming existing `P00N-*` directories on disk. They belong to entities the clean break marked legacy; nothing renames them.
