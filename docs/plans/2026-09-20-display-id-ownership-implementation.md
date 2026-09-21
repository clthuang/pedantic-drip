# Structural Identity — Implementation Plan

**Design:** [2026-09-20-display-id-ownership-design.md](./2026-09-20-display-id-ownership-design.md) (rev 3 — clean break)
**RCA:** [../rca/20260920-display-id-ownership.md](../rca/20260920-display-id-ownership.md)

32 subtasks in 3 releases (26 headings; C8–C12, C15–C16 and C19–C20 are grouped). Release B does **not** close before Release C — see C22. Each carries a **Contract** (what it guarantees), an **Interface** (exact signatures/schemas it changes), and a **Verify** step that is objectively checkable and fails before the work is done.

> **Status — Release A shipped 2026-09-21 (`96b2f88a`), plus C20a (`12f1b571`). Releases B and C not started.** This plan remediates the entity registry **as it stands on 2026-09-20** (schema_version 3, generation v2). It survived five adversarial review rounds — one native reviewer and four Codex passes — and every blocker from rounds 1-3 is absorbed. Round 4's findings are absorbed except where noted inline.
>
> A ground-up redesign of the identity model is under consideration; if that proceeds, most of Release C is superseded. **Release A is worth shipping regardless** — it is non-destructive, depends on nothing else, and repairs a reconciliation path that is currently dead.
>
> Companion documents: [RCA](../rca/20260920-display-id-ownership.md) · [design](./2026-09-20-display-id-ownership-design.md) · [live schema](../entity-schema.html)

**Not estimated.** Re-derive after Release B.

## Conventions

- **Verify must discriminate.** A check that passes on today's tree is not a check. Where a proof is stateful, the fixture is rebuilt every run.
- **Status writes go through `append_phase_event()`.** This binds **B6**'s archival. Note the guard is weaker than it sounds: `check_status_write_path` is **warning-only** — "doctor's overall exit code is unaffected" (`check_status_write_path.py:13`) — and is a static grep over `hooks/lib` + `mcp` only. The enforcing gate is the pytest static-grep in `test_event_sourced_state.py`. Neither can see a one-off `sqlite3` UPDATE run in a terminal.
- **Snapshots use `.backup`, never `cp`** — the DB is in WAL mode (`database.py:10477`).

```bash
sqlite3 ~/.claude/pd/entities/entities.db ".backup '/tmp/pd-pre-structural.db'"
sqlite3 /tmp/pd-pre-structural.db "PRAGMA integrity_check; SELECT COUNT(*) FROM entities;"
```

---

# Release A — non-destructive reconciliation fix — **SHIPPED `96b2f88a`, 2026-09-21**

**Delivered scope differed from the plan below, deliberately.** A1 additionally removed the `backlog.md` parse-back loop, which made `_sync_backlog_entities` empty, so the helper and its dispatch entry are gone. Rationale: backlog is DB-only (`add-to-backlog.md:8,17`) and `backlog.md` is a gitignored projection whose ID column is re-rendered `{seq:05d}`; parsing it back made a lagging, lossy rendering authoritative over the DB that produced it. Five rows in the live projection resolve to no entity, one of which (`00278`) is a live item re-rendered.

**A2 was narrower than written.** Verified empirically: `update_entity` re-resolves its target by `(workspace_uuid, type_id)`, so an unscoped read **cannot** produce a cross-workspace write — a foreign `type_id` raises `ValueError`, swallowed at the archival branch. A2's guarantee is read scope; the test asserts the read.

**A3 gained the creation assertion** (zero `upsert_entity`/`register_entity` calls), without which the defect above ships green.

## A1 — Remove every text-shape deletion criterion

**Contract.** After A1 no code path deletes an entity based on the textual shape or textual grouping of its identity. The deletable set strictly shrinks; nothing new becomes deletable. FK and event-retention behaviour are unchanged (#081 untouched).

**Interface.** Two paths, not one — A3's zero-delete guarantee is unsupported without both:

- `_cleanup_junk_backlogs(db, entities)` (`entity_status.py:224`) and `JUNK_ID_RE` (`:20`) **removed**, with its call site in `_sync_backlog_entities` (`:272`) deleted.
- `_dedup_backlogs(db, entities)` (`:243`) — groups by **textual id** (`:253`) and calls `delete_entity` (`:265`). Either removed or re-keyed onto `(workspace_uuid, uuid)`; grouping by id text across workspaces is the same defect in a second place.

No replacement criterion. "Absent display row" and "absent source" are both unsafe — 180 legitimate entities lack display rows, and backlog is DB-only (`add-to-backlog.md:8,17`).

**Verify.** `grep -rc "JUNK_ID_RE\|_cleanup_junk_backlogs" plugins/pd/hooks/lib/` → 0 outside tests; no `delete_entity` call remains reachable from `sync_entity_statuses`.

**Depends.** Nothing.

## A2 — Scope backlog reads to the workspace

**Contract.** Backlog reconciliation reads only the invoking workspace's entities. A workspace-scoped call never sees another workspace's rows.

**Interface.** `_sync_backlog_entities(db, full_artifacts_path, artifacts_root, project_id, workspace_uuid=None)` (`:272`) passes `workspace_uuid` to its reads at `:291` and `:298`, which today use `project_id` alone — and an absent legacy filter means an unscoped read (`database.py:6607`).

**Verify.** Two workspaces holding identical entity ids; assert the scoped call returns only its own rows. Today it returns both.

**Depends.** A1. *(Retargeted: the earlier A2 modified the exception handler of the function A1 deletes — the two could not coexist.)*

## A3 — Prove no deletions, across four fixtures

**Contract.** Reconciliation invokes `delete_entity` zero times under every scoping and data condition below, and completes successfully with per-row continuation.

**Interface.** Test-only. Spy on `EntityDatabase.delete_entity`.

**Verify.** Assert **zero delete calls** — not survival. Survival on a live copy is guaranteed by the event FK and is therefore not evidence.

1. workspace-only invocation (`workspace_uuid` set, `project_id=None`);
2. identical entity ids in two workspaces;
3. entities missing display rows and missing source files;
4. entities with and without event history.

Also assert correct workspace selection and that a failure on one row does not abort the remaining rows. **Do not alter the FK to make this pass.**

**Depends.** A1, A2.

# Release B — detection and the clean break

## B1 — AST detector for text inference

**Contract.** Given a Python module, the detector yields every site that derives identity, kind, or structure from the *text* of an `entity_id` or `type_id`. It never fires on comments or docstrings, and never grants exemption by function-name prefix.

**Interface.** New in `doctor/test_audit_writes.py`, replacing `_AUDIT_PATTERN` (`:480-485`):

```python
@dataclass(frozen=True)
class InferenceSite:
    path: str; lineno: int; idiom: str   # "regex" | "split" | "slice" | "startswith" | "sql"

def iter_inference_sites(tree: ast.AST, path: str) -> Iterator[InferenceSite]: ...
```

Idioms covered: compiled-pattern `.match/.search/.fullmatch`, `re.match(pattern, <id>)`, `.partition(":")`/`.split(":")` including subscript receivers (`entity["type_id"].split(...)`), dash-index slicing (`entity_id[:i]`), `startswith("feature:")`, and SQL `substr`/`instr` over `entity_id`.

**Verify.** Positive/negative fixture pairs, one per idiom. Negative set must include `_UUID_RE.match`, `_TAG_RE.match`, `_TASK_HEADING_RE.match`, `_WORKSPACE_UUID_RE.match` and `database.py:7768`'s docstring — all must **not** fire.

**Depends.** Nothing.

## B2 — Widen scan roots to templates

**Contract.** The audit covers UI templates, which currently sit outside `_SCAN_ROOTS` (`:475`).

**Interface.** `_SCAN_ROOTS` gains the template directory; a template-expression extractor feeds `iter_inference_sites`.

**Verify.** `_card.html:4` and `:10` are reported.

**Depends.** B1.

## B3 — Turn the lint red and remove grace mode

**Contract.** The audit **fails** on the current tree, naming every known site, and `xfail` grace mode is gone.

**Interface.** The audit test asserts an empty site list against an explicit allowlist of sanctioned boundaries (migration functions named in policy, not by prefix).

**Verify.** The run fails and names at minimum: `rebuild_tool.py:1031`, `database.py:7302`, `database.py:7436` (slicing — no regex reaches it), `database.py:10281`, `engine.py:376`, `frontmatter_inject.py:82`, `workflow_state_server.py:485`, `router.py:358`.

**Non-vacuity gate:** if it passes, the detector is wrong — fix B1, do not proceed.

**Depends.** B1, B2.

## B4 — Establish the high-water mark (design D0a)

**Contract.** Every bucket's `sequences.next_val` exceeds the true maximum issued number for that bucket, **including legacy rows invisible to the display join**. After B4 the counter alone guarantees no reissue, and the census is only a repair floor. Idempotent: a second run changes nothing.

**Interface.** One-time migration-boundary function. This is the **only sanctioned parse of legacy ids in the entire plan**, declared explicitly in B3's policy allowlist — not granted by a `_migration_13_*` name prefix.

```python
def establish_high_water(conn) -> dict[tuple[str, str], int]:   # (kind, workspace_uuid) -> new next_val
```

**Contract addendum.** `next_val = max(stored_next_val, computed)` — **never assignment**. The whole sweep runs inside a single `BEGIN IMMEDIATE`; the `conn` signature below cannot use `db.transaction()`, and a read-modify-write on `sequences` racing `next_sequence_value`'s own `BEGIN IMMEDIATE` (`database.py:10261`) silently loses the allocator's increment.

**Verify.** For every bucket, `next_val > max(parsed legacy seq, display seq)`. Assert on **all seven workspaces holding `sequences` rows** (`69696982, d373a5ad, f7b49c1d, 35d9b5f9, 6f113c48, 7e788234, fe180347`) — 24 workspace rows exist in total; "six" was wrong in three places. The returned mapping must cover every `(kind, workspace)` present in `entities` ∪ `sequences` — **19 buckets today**.

**Non-vacuity gate.** A no-op `establish_high_water` passes on 17 of the 19 live buckets; only the two project buckets in `fractorg` and `project_illium` discriminate. Force drift instead: set every `next_val` to 1 on a fresh fixture and assert all 19 are raised. Then interleave a real allocation **between** the two idempotence runs — assignment and `max()` are indistinguishable back-to-back, and diverge only there.

**Brainstorm carve-out.** The brainstorm bucket's counter holds a **date** (`20260711`), because `_seed_sequences` ran a generic `^(\d+)` parse over date-prefixed ids. No brainstorm creation path calls the allocator — ids come from the filename (`commands/brainstorm.md:14`) — so the row is vestigial. Do not "repair" it toward a real date; state that brainstorm is out of the monotonic-sequence model.

**Depends.** Nothing.

## B5 — Select the archival set

**Contract.** A pure, re-runnable selector returns exactly the entities to archive. Selection is **by the archival marker's absence**, not by terminal status — 168 of the 180 rows were already terminal, so status cannot distinguish "archived by the break" from "already dropped". Returns 180 before B6 and 0 after.

**Interface.** `select_legacy_entities(conn) -> list[LegacyRow]`, `LegacyRow = (uuid, kind, entity_id, status)`. No writes.

**Verify.** Emit the selected set **grouped by `(workspace_uuid, kind, status)`**, not as a single total — the totals (166 backlog + 3 brainstorm + 1 feature + 10 project = 180) are measured on a shared registry that 23 other workspaces keep writing to, and every project created anywhere before B5 runs adds a display-less row. Asserting the literals invites re-baselining whatever drift appeared.

**Release blocker.** Any **non-terminal** row outside the invoking workspace requires a named owner before B6 runs. Today that set is non-empty:

| workspace | kind | entity_id | status |
|---|---|---|---|
| `/Users/terry_agent` | project | `P001` | **active** |
| `/Users/terry_agent` | project | `P001-agent-orchestrator` | **active** |
| `/Users/terry_agent` | feature | `unnamed-b43fd0f1` | NULL |
| `cast-below` | brainstorm | `original-ideation-prd` | NULL |
| `cast-below` | project | `P001` | completed |

C22 recreates via "ordinary creation paths", which run in the *current* project's context — nothing recreates another repo's entities. **Design D0's scope table counts NULL as terminal**, which is how it reports "0 to recreate" for brainstorm and feature; production's own `TERMINAL_STATUSES = {promoted, abandoned, archived}` (`entity_status.py:10`) does not.

After B6, returns 0 — the idempotence proof, and it fails today.

**Depends.** B4.

## B6 — Archive durably, and make it stick

**Contract.** Every selected entity carries a durable archival marker, retains its row, uuid, history and parent links, and keeps its `entity_id` unchanged. No number is freed. Reconciliation does not revert it.

**Interface.**
- Marker: **a tag** (`entity_tags`), not a metadata key and not status alone. Metadata is not a safe carrier: `update_entity` shallow-merges, so the only removal path is `metadata={}`, which nulls the entire blob — destroying `features`/`milestones`/`brainstorm_source` written at `feature_lifecycle.py:293-298` and read by `_project_meta_json`. It also emits `metadata warning: Unknown metadata key` on every write until registered in `entity_registry/metadata.py`.
- Status write, where used, goes through the real signature — `append_phase_event(*, type_id, project_id, event_type="entity_status_changed", workspace_uuid, metadata={"new_status": ...})` (`database.py:9153`), which applies `metadata["new_status"]` at `:9302`. *(The earlier draft's `entity_uuid=/axis=/to_value=` kwargs were invented and do not exist.)*
- **Reconciliation authority:** `_sync_meta_json_entities` writes `.meta.json` status back over the entity when they differ (`entity_status.py:84-88`), so archival is reverted at the next session start for any entity whose artifact survives — every legacy project. Either retire the artifact or make the marker take precedence.

**Note:** the lifecycle machine does *not* permit these transitions — `MACHINE_REGISTRY['backlog'].validate('open','archived')` returns `allowed=False`, and `project` has no `archived` phase at all. `append_phase_event` does not consult the machine (validation lives at `router.py:452`), which is how 26 backlog rows are already `archived`. B6 therefore needs an explicit archival policy, not an assumed legal transition.

**Verify.** Assert the **selected uuids'** resulting marker state, the expected events, unchanged `entity_id` values, and a clean second run. Integrity checks and unchanged parent counts all pass if archival does nothing — they are necessary, not sufficient. Then run reconciliation and assert the marker survived.

**Depends.** B5.

## B7 — Exclude archived from live projections

**Contract.** Marked entities do not appear in the Kanban board, `backlog.md`, or list tools. Their numbers remain reserved by the counter.

**Interface.** Status/marker filters in the projection writers. **No change** to C1's census.

**B7 also owns the `backlog.md` renderer.** `_project_backlog_md` re-pads every id to `f"{d['seq']:05d}"` (`workflow_state_server.py:739`) and reads **unscoped across all workspaces** (`:633`). That rendering is what made `00063` — an id belonging to a different, archived entity — the visible identity of the live `063-watch-…` row; 5 rows in the current projection resolve to no entity at all. The read-back half of that loop is already gone (Release A deleted the parser), so it can no longer create entities; it remains a lossy, colliding projection. Render the real `entity_id` and scope the read.

**Verify.** `backlog.md` shows only live items. The reservation assertion belongs to B4 and is checked there — not deferred to C1, which depends on B6 and would make this a forward dependency.

**Depends.** B6.

---

# Release C — atomic cutover (C1–C21 ship together)

Three ordering hazards, restated with real task ids (they were written in a `T`-numbering the plan no longer uses, and the `Depends` lines — which `Sequencing` designates authoritative — encode none of them):

- **C3 before C6** leaves a build where an old non-strict write creates an entity without a display row (`database.py:7435`), the completeness guard correctly refuses, and allocation stops repo-wide.
- **C6 before C15** reopens the duplicate project-identity window.
- **C6 before C18** leaves the startup producer minting non-canonical ids.

All three are now carried as explicit `Depends` edges on C3, C15 and C18. The mixed-version writer problem this preamble used to raise in passing is now **C23**, which owns it.

## C1 — Structural census

**Contract.** Returns the highest issued `seq` for a `(kind, workspace_uuid)` bucket from structure, never from text. Counts entities of **all statuses**, including archived.

**Interface.** `_census_max(conn, *, kind: str, workspace_uuid: str) -> int | None` —
`SELECT MAX(d.seq) FROM entities e JOIN entity_display d ON d.uuid=e.uuid WHERE e.kind=? AND e.workspace_uuid=?`

**Scope.** Display-bearing rows only. Archived legacy rows are invisible to this join by construction; their numbers are reserved by the counter (B4), not by the census.

**Verify.** A bucket whose only rows are `P{NNN}-{slug}` **with display rows** returns `N`, not `None`. Today's `re.match(r"^(\d+)", eid)` returns nothing for those.

**Depends.** B5.

## C2 — Monotonic issuance

**Contract.** `next_sequence_value` returns `max(stored_next_val, census_max + 1)` and **never returns a value ≤ any previously issued value for that bucket**. Archiving the highest-numbered entity does not lower the next value. Gaps are permitted and never reclaimed.

**Interface.** `next_sequence_value(self, project_id=None, entity_type=None, *, workspace_uuid=None) -> int` — signature unchanged, contract strengthened. `re.match(r"^(\d+)", eid)` (`:10281`) deleted.

**Verify.** Fresh fixture every run — the unchanged allocator increments even when the assertion fails (`:10291`), so a reused fixture returns `[134, 135]` and passes green with no implementation change.
```bash
rm -f /tmp/drifted.db && sqlite3 <backup> ".backup '/tmp/drifted.db'"
sqlite3 /tmp/drifted.db "UPDATE sequences SET next_val=134 WHERE entity_type='feature' AND workspace_uuid='69696982-...';"
# first allocation on the FRESH fixture returns 135
```
Plus **monotonicity pin**: archive the highest-numbered feature, allocate, assert the value did not drop.

**Depends.** C1.

## C3 — Fail-closed completeness guard

**Contract.** Allocation refuses when its bucket has **non-marker-archived** entities lacking display rows. The predicate is **B6's tag**, not `status`: `_sync_meta_json_entities` writes `.meta.json` status back over the entity whenever they differ (`entity_status.py:84-88`), and `"archived"` is not in `STATUS_MAP`, so a status-based predicate flips back at the next session start and C3 then refuses forever. Archived legacy rows neither satisfy nor violate the guard — scoping it to all entities would refuse every bucket the clean break touches, including the ones B6's replacements need. An empty bucket is complete. No census maximum means zero; an absent counter starts at one. The check examines existing entities, never the pending allocation. Failure rolls back **without advancing the counter**. Repair happens outside the transaction — no recursive migration or registration while holding the write lock.

**Interface.** Private helper called inside the existing `BEGIN IMMEDIATE` (`:10261`); raises a typed error.

**Verify.** Fresh DB allocates `1` (empty bucket is complete). A bucket with one display-less entity refuses **and** leaves `sequences.next_val` unchanged — assert the counter, not just the exception.

**Live-precondition gate (not synthetic).** Both checks above are fixture-only and pass regardless of the production state. Immediately before cutover, assert `select_legacy_entities(live_conn)` returns 0 against the **live** DB; if not, re-run B6 first. Without this, C3's precondition is established once by B6 and then regresses continuously: `init_project_state` passes `_strict_id_format=False` (`feature_lifecycle.py:321`) and `register_entity` writes the display row only `if strict:` (`database.py:7435`), so every project created between B6 and C6 is non-archived **and** display-less.

**Depends.** C2, **C6**.

## C4 — Single display-id renderer

**Contract.** Exactly one function converts `(kind, seq, slug)` to a display string. Allocator and registrar cannot disagree.

**Interface.** `render_display_id(kind: str, seq: int, slug: str) -> str`. Call sites `entity_server.py:691` and `id_generator.py:68`, which independently hardcode `f"{seq:03d}-{slug}"`, both route through it.

**Verify.** AST count of executable f-strings producing `{seq:03d}` → exactly 1 (a textual `grep -c` also counts documentation examples) — **plus a table-driven assertion of rendered output for each production kind.** The count alone is satisfied by consolidating two identical kind-blind bodies into one kind-blind function, which is exactly the bug: today the project `P` prefix comes from neither call site but from the caller, `init_project_state` (`feature_lifecycle.py:314`), and C7 removes `entity_id` from the signature, so the prefix loses its owner.

**DECIDED 2026-09-21 — the `P` prefix is dropped.** Projects render `{seq:03d}-{slug}`, identical to every other sequence-numbered kind. `render_display_id` therefore has no kind-specific branch for projects at all.

This removes the special case that caused the original incident: `_PROJECT_DISPLAY_RE = ^P(\d+)$` existed only to parse the prefix back off, and its end anchor is what silently returned 0 for every slug-suffixed project id. Two workspaces (`fractorg`, `project_illium`) already use the prefix-free shape, so this makes them canonical rather than exceptional.

Consequences to carry:
- `create-project.md` must stop instructing "build `P{NNN}` from the returned `seq`" and stop discarding the returned `entity_id`.
- The `P{NNN}-*` directory guard in `create-project.md` no longer matches; it becomes `{NNN}-*`.
- `_PROJECT_DISPLAY_RE` and the `kind == "project"` branch in `_display_number` (`rebuild_tool.py:1026-1034`) are deleted, not repaired.
- Existing `P00N` directories on disk keep their names — they belong to entities the clean break archives, and nothing renames them.

**Brainstorm is excluded from this renderer.** Its identity is a timestamp (`{YYYYMMDD-HHMMSS}-{slug}`, `commands/brainstorm.md:14`), not a sequence, and no brainstorm path calls the allocator.

**Depends.** Nothing.

## C5 — `register_entity` takes structured identity

**Contract.** Registration accepts `seq` and `slug` as data, writes the `entity_display` row from them, and derives `entity_id` via C4. Every successful registration produces a display row — unconditionally, not `if strict:`.

**Interface.**
```python
def register_entity(self, entity_type: str, *, seq: int, slug: str, name: str,
                    workspace_uuid=None, artifact_path=None, status=None,
                    parent_uuid=None, metadata=None) -> str
```
Removed: `entity_id: str`, `_strict_id_format`, `parent_type_id`, `project_id`. **No alias** — an alias parsed inside a `_migration_13_*`-named helper would be auto-approved by the audit (`test_audit_writes.py:542`).

**Verify.** Force `PD_REGISTER_ENTITY_STRICT_ID_FORMAT=1` (the suite defaults it **off** at `conftest.py:37`, so the production path is otherwise never exercised), seed the workspace, register a project, assert success and read back **both** the entity and its display row. A substring check on the error is vacuous — `_process_register_entity` converts every exception to a string (`server_helpers.py:320`).

**Depends.** C4.

## C6 — Delete the registration parsers

**Contract.** No parsing remains on the registration path.

**Interface.** Delete `_ENTITY_ID_FORMAT_RE` (`:3960`), its gate (`:7302`), the slicing parser (`:7436-7438`), and `_strict_id_format=False` at `feature_lifecycle.py:321`.

**Verify.** B3's lint reports zero sites in `database.py`'s registration path; `grep -rc "_strict_id_format" plugins/pd --include=*.py` → 0 outside tests. Update `test_feature_lifecycle.py:440`, which asserts the bypass is present.

**Depends.** C5.

## C7 — Migrate all `register_entity` callers

**Contract.** Every caller supplies `seq`/`slug` **from a structured source**, never by parsing. Upsert idempotence is preserved. Workspace and parent resolution, currently carried by the dropped aliases, are re-homed explicitly.

**Interface.** Not call-site changes only — three upstream contracts must change first:

- `generate_entity_id()` (`id_generator.py:41,62`) returns a **string**, discarding `seq`/`slug`. It must return both, or callers cannot supply them without parsing.
- MCP `register_entity` (`entity_server.py:512`) accepts `entity_id`. Its tool surface changes to `seq`/`slug`.
- `upsert_entity` (`database.py:7553`) takes textual identity, forwards it to registration (`:7601`) and uses it for **conflict lookup** (`:7628`). The lookup key must move to structured identity without breaking three-branch insert-or-update semantics.

Re-homing the dropped aliases: `project_id` resolves workspace identity at `database.py:7315`; `parent_type_id` performs workspace-scoped parent resolution including missing-parent behaviour at `:7332`. Each migrated boundary names where those now happen.

`create_key_result` (`entity_server.py:1452`) generates a name-derived id with no recoverable sequence; it obtains a real allocation.

**Site count.** The three upstream contracts above are necessary but not the whole surface: roughly **15** production sites call `register_entity`/`upsert_entity`/`register_entities_batch`, including `backfill.py:439,566,613,731,833`, `feature_lifecycle.py:205,312`, `task_promotion.py:367`, `entity_server.py:471,853`, `server_helpers.py:278` and `database.py:10432`. Several mint ids with **no recoverable sequence** (filename stems, timestamps), so "supply `seq`/`slug` from a structured source" is a real design question at each, not a mechanical edit. Enumerate and classify them before estimating.

**Verify.** Full suite green; no caller constructs an `entity_id` string; upsert idempotence has its own red-first test (same identity twice → one row, status updated).

**Depends.** C5, C6.

## C8–C12 — Readers adopt their contracts

Each subtask takes one row of design D5. **Contract:** the reader returns the same output as today for valid data, sourced structurally. **Interface:** the site's own signature is unchanged; only its *source* moves, per the table below — these are five separate subtasks, one per row. **Verify:** an output-contract assertion per category — "lint green plus an artifact-path test" would pass after deleting the parsing while returning wrong fields.

| # | Need | Source | Sites |
|---|---|---|---|
| C8 | kind | `entities.kind` | `router.py:358,421`; `frontmatter_sync.py:109`; `workflow_state_server.py:1113,1395` |
| C9 | seq / slug | `entity_display(uuid)` | `frontmatter_inject.py:82`; `workflow_state_server.py:485,675` |
| C10 | parent kind + **opaque** identity | `parent_uuid` → parent row → `kind` + stored `entity_id` (design D9); parent *display* only when present | `frontmatter_inject.py:103`; `frontmatter_sync.py:125` |
| C11 | artifact path | `entities.artifact_path` | `engine.py:366` + 7 callers |
| C12 | rendered width / re-kind | C4 renderer; regenerate key from columns | `workflow_state_server.py:410`; `database.py:7815` |

C8 note: `router.py:352` already fetches the entity row carrying `kind`, then splits the string three lines later. `workflow_state_server.py:452` likewise reads `entity["kind"]` and parses anyway at `:485`.

C10 note: D0 leaves three live children attached to **archived parents that have no display row**. Reading the parent's stored `entity_id` opaquely (as `frontmatter_inject.py:90` does today) is a column read, not inference; decomposing it into seq/slug is. Add the retained-lineage fixture explicitly.

**C11 caveat.** The design justifies this move on `artifact_path` being "100% populated". That is true and it is the wrong property: `_extract_slug` returns a **slug**, `artifact_path` is a **path**. Measured over 271 features — 0 empty, but **54 carry a trailing slash** (so a naive `basename` yields `""`) and **109 are absolute vs 162 relative**. C11 needs a normalisation contract, not just a source swap.

**Verify (all five):** use fixtures where the textual id **disagrees** with the structured data, and assert the structured result. Asserting unchanged output alone passes today's text-parsing readers.

**C8–C12 fallback caveat.** "Textual id disagrees" does not defeat `_read_entity_display` (`workflow_state_server.py:371-421`), which falls back to `metadata["id"]`/`metadata["slug"]` with only a stderr warning. A fixture must disagree on **all three** — textual id, display row, and metadata — or the fallback silently supplies the right answer.

**Depends.** C5.

## C13 — Missing parent reports and defers (design D8)

**Contract.** An unresolvable parent produces a diagnostic. No synthetic entity is minted from parsed text.

**Interface.** `_register_synthetic_for_missing_parent` (`backfill.py:630`) removed; `_derive_parent`'s text path (`:680`, `:691`) and `backfill.py:752` retired.

**Verify.** First import with an absent parent produces a diagnostic and creates nothing. Today it mints a synthetic entity.

**Depends.** C5.

## C14 — Prose guards and stale commentary

**Contract.** No command doc describes drift the allocator can no longer produce. The directory cross-check is **retained** — `create-feature.md:19` creates the directory before registration, so an unregistered directory from a partial failure is invisible to a DB census.

**Interface.** `create-feature.md:18`, `create-project.md:18`; comments at `rebuild_tool.py:1021-1023`, `feature_lifecycle.py:306`, `display.py:32`, `entity_server.py:645`.

**Verify.** `grep -rc "sequence drift" plugins/pd/commands/` → 0; `./validate.sh` clean.

**Depends.** C2.

## C15–C16 — One owner for project registration

**C15 Contract.** Exactly one code path *attempts* project registration. **Interface:** remove the duplicate registration; `init_project_state` (`feature_lifecycle.py:312`) owns it. **Verify:** count registration **attempts** and creation events, not resulting rows — a duplicate registration followed by conflict handling also yields exactly one row.

**C16 Contract.** Registration precedes directory creation, so a registration failure leaves no directory. **Interface:** adding `parent_uuid` is not sufficient — `init_project_state` currently *rejects a nonexistent directory before registering* (`feature_lifecycle.py:281-283`), and the command creates the directory first (`create-project.md:20`). The precondition and the internal ordering must both change: validate the path, register, then create. **Verify:** inject a failure that actually **reaches registration** — a failure caused by passing a nonexistent directory proves nothing — and assert no directory exists afterwards.

**Depends.** C15 depends on C5 **and C6**; C16 depends on C15.

## C17 — One workspace identity through allocate and register

**Contract.** Allocation and registration at every production call site resolve the **same** workspace value. This is a caller-level invariant, not an enforced one: `next_sequence_value` returns a bare `int` and `register_entity` takes `seq`, `slug` and `workspace_uuid` independently, so nothing binds a number to its issuing workspace, and `entity_display` has only a uuid primary key with a non-unique seq index (`database.py:4168`). An adversarial cross-workspace registration therefore cannot be made to fail without allocation provenance — which is out of scope here.

**Interface.** `task_promotion.py:354` (allocate) and `:374` (register); `entity_server.py:839` and `:857`.

**Verify.** Assert both call sites pass one resolved workspace value through allocate and register — a caller-level regression test, not a rejection test.

**Depends.** C2.

## C18 — Canonicalize the startup backfill

**Contract.** `run_backfill` produces canonical identities or nothing. It cannot mint bare `P{NNN}`.

**Interface.** `backfill.py:566` (upsert) and `:511` (lookup omitting the slug); invoked at `entity_server.py:273`.

**Verify.** State it as an invariant, not as the string `P`: **every entity `run_backfill` creates has an `entity_display` row and an `entity_id` equal to `render_display_id(kind, seq, slug)` (C4)**, and `run_backfill` leaves the project row count unchanged.

The string form is defeated by a second producer in the same function. `_scan_projects` (`backfill.py:558-563`) reads the display row and, when present, sets `proj_entity_id = str(row["seq"])` — dropping the slug, where the feature twin reattaches it (`:598-602`). Post-C5 that yields `entity_id="5"` → `project:5`, which contains no `P` and passes both halves as originally written. Two live projects (`fractorg`, `project_illium`) already carry project display rows, so the branch is reachable **today**, not only after cutover.

**Depends.** C5, **C6**.

## C19–C20 — Rebuild seeds from structure

**C19 Contract.** Rebuild carries structured display data through the uuid remap instead of re-parsing. **Interface:** `rebuild_tool.py:615`, `:1107`. **Verify:** a rebuild of a DB containing `P{NNN}-{slug}` preserves `seq`/`slug` exactly.

**C20a — SHIPPED `12f1b571`, 2026-09-21 (pulled into Release A scope).** `_seed_sequences` now returns `max(stored_next_val, derived_max + 1)` and carries counter-only buckets across. It has no dependency on C1 or C19, and Release B without it leaves every archived number reissuable by the next rebuild. Verified read-only against the live registry: 19 buckets in, 19 out, 0 lowered, 0 dropped.

**C20b Contract.** Seeding preserves the stored high-water mark rather than deriving solely from entity rows (`:1044`) — monotonicity depends on it. **Interface:** `_seed_sequences` (`:1045`, `:1051`). **Verify:** rebuild a DB whose counter exceeds its census max, **and** a bucket with a counter but zero entity rows — rebuild enumerates buckets from entities (`rebuild_tool.py:1044`), so a counter-only bucket is the case that silently loses its reservation. Assert neither counter is lowered.

**Depends.** C19 depends on C1; C20 depends on C19.

## C22 — Recreate the live remainder

**Contract.** The **15 live rows** identified in [entity-archive-manifest.md](../entity-archive-manifest.md) — 6 open backlog items, 7 project rows across three workspaces, 1 brainstorm and 1 feature — exist in the new shape with fresh uuids, display rows, and **newly issued** numbers. No recreated entity reuses an archived entity's number.

**Interface.** Ordinary creation paths only (`/pd:add-to-backlog`, project creation) — through the *new* writer. No bespoke insert.

**Verify.** Each new entity has an `entity_display` row; **DECIDED 2026-09-21 — duplicate project pairs collapse onto the most recent row, and all children re-parent to it.** Three pairs are the same project registered twice (`P002`/`P002-memory-flywheel`, `P003`/`P003-entity-system-redesign`, `P001`/`P001-agent-orchestrator`), with children split across both halves. The surviving row is the one with the later `created_at`; every child of the other half re-parents to it via `parent_uuid`, which is a uuid foreign key and needs no text.

**Verify.** Each new entity has an `entity_display` row; every issued `seq` exceeds the bucket's pre-break high-water mark recorded by B4; after the pair collapse **no entity retains a `parent_uuid` pointing at a non-surviving half**, and the total child count per collapsed pair is preserved (5+0, 4+1, 12+3 today). The **4** live children remain attached to their archived parents (79 children total hang off display-less parents; 4 are non-terminal under production's `TERMINAL_STATUSES` — the count of 3 assumed NULL was terminal). **This Verify covers only entities C22 created and is structurally incapable of detecting the set never created** — that gap is B5's grouped release blocker.

**Depends.** C5, C7, C15–C16. *(This was Release B's recreate step. It cannot close inside Release B — recreating through the new writer requires the cutover, so "all of B closes before C" was never achievable.)*


## C23 — Old builds must fail loudly, not write quietly

**Contract.** A process running a pre-cutover build cannot write to a post-cutover file. It fails with a clear error instead.

**Interface.** Release C bumps `schema_v2.V2_SCHEMA_VERSION` (the paired `assert max(V2_MIGRATIONS) == _V2_SCHEMA_VERSION` at `database.py:6217` already gives the bump a home), plus a write-path assertion in `EntityDatabase.__init__`: if the file's `schema_version` exceeds this build's known max, raise on write.

**Why it needs an owner.** The plugin is installed once, globally, and shared by all 24 workspaces; updating it does not restart running MCP servers. `_migrate_v2` loops `range(current + 1, target + 1)` (`database.py:10555`), so a file stamped *above* this build's max iterates zero times and proceeds to write normally — there is no read-side version assertion anywhere on the write path. An old `entity_server` keeps calling the old `register_entity(entity_id=…, _strict_id_format=False)`, bypassing C3's guard and minting exactly the display-less rows that then trip C3 for every new process. `run_backfill` fires at every MCP start (`entity_server.py:271-273`) and `sync_entity_statuses` at every session start (`reconciliation_orchestrator/__main__.py:117-122`); both swallow exceptions into results, so an old writer emits no signal.

**Verify.** Open a file stamped one version above the build's max; assert reads succeed and the first write raises. No subtask Verify can observe a *different process running different code*, so this is the only available proxy — state that limitation rather than implying coverage.

**Depends.** Nothing. Ships early in Release C, before C5.

## C21 — Lint green, battery green

**Contract.** The audit passes with no `xfail`, having been red at B3.

**Interface.** None — verification only.

**Verify.**
```bash
pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q
./validate.sh
pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q
bash plugins/pd/hooks/tests/test-hooks.sh
```
Baseline: 3842 passed / 3 skipped, hooks 66/66, validate 0/0.

**Depends.** C6, C7, C8–C12, C13, C14, C15–C16, C17, C18, C19–C20, C22, C23. *(Not "all of Release C", which included itself.)*

---

## Sequencing

The explicit `Depends` lines are authoritative; this diagram is derived from them.

```
Release A   A1 ── A2 ── A3          SHIPPED 96b2f88a
            C20a (no deps)          SHIPPED 12f1b571

Release B   B1 ── B2 ── B3
            B4 ── B5 ── B6 ── B7

Release C   C23 (no deps, ships first)
            C1 ─┬─ C2 ─┬─────────────── C3    ← also needs C6
                │      ├─ C14 ─┐
                │      └─ C17 ─┤
                └─ C19 ── C20b ┤
            C4 ── C5 ── C6 ─┬─ C7 ─┬─ C22 ─┤
                            ├─ C8–C12 ─────┤
                            ├─ C13 ────────┼─ C21
                            ├─ C15–C16 ────┤
                            ├─ C18 ────────┤
                            └─ C3 ─────────┘
```

C6 is now a predecessor of C3, C15 and C18 — the three hazards the Release C preamble named but the graph did not encode. C3 therefore sits on both the C2 and C6 chains.

## Out of scope

- The 22 historical duplicate feature numbers. Inert; repair would rename live directories and branches.
- Resolving #081 (hard delete vs append-only history). A1–A3 explicitly do not touch it.
- The v2 `sequences` shape divergence (RCA S8) — no live importer.

## Risks

- **B5 is a data migration on a shared multi-project DB.** `.backup` first, integrity checks after, recount all five other workspaces.
- **B7 and C1 pull in opposite directions** — archived rows are hidden from projections but must remain in the census. Assert both; do not "simplify" later. **Consider eliminating this tension rather than managing it:** give the 180 archived rows `entity_display` rows during B6, using the seq B4 already parses. C1's census then covers them (satisfying its Contract's "all statuses, including archived", which its own Scope note currently contradicts), B7 hides them by the tag rather than by absence of a display row, and rebuild reseeds from structure with no counter dependency.

- **Release B has no rollback.** There is no `V2_MIGRATIONS_DOWN` (only the v1 chain's, `database.py:5944`). Un-archiving is a *forward compensating write* — sanctioned, since `update_entity` routes through `append_phase_event` and neither the lifecycle machine nor a status CHECK blocks the reverse — but it costs ~360 permanently immutable `events` rows for a fully-reverted operation, and nothing can ever be deleted, so a B-then-rollback leaves both the archived originals and C22's recreations forever. `.backup` is **not** a rollback: it is one shared file across 7 workspaces with entities, so restoring it reverts six unrelated repos, and it violates this plan's own monotonicity rule by resetting counters below numbers already on disk as directories and branches. Release B needs an explicit compensating-write procedure and a statement of the event-log cost it accepts.
- **C5 and C7 must land together.** The largest single unit; rehearse on a copy.
- **Ordering violations are silent.** Release C before B leaves an under-populated census; monotonic `max(stored, …)` limits the damage but does not license skipping the order.
