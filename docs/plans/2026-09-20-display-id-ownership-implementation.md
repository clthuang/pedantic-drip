# Structural Identity — Implementation Plan

**Design:** [2026-09-20-display-id-ownership-design.md](./2026-09-20-display-id-ownership-design.md) (rev 3 — clean break)
**RCA:** [../rca/20260920-display-id-ownership.md](../rca/20260920-display-id-ownership.md)

32 subtasks in 3 releases (26 headings; C8–C12, C15–C16 and C19–C20 are grouped). Release B does **not** close before Release C — see C22. Each carries a **Contract** (what it guarantees), an **Interface** (exact signatures/schemas it changes), and a **Verify** step that is objectively checkable and fails before the work is done.

> **Status — preserved, not yet started.** This plan remediates the entity registry **as it stands on 2026-09-20** (schema_version 3, generation v2). It survived five adversarial review rounds — one native reviewer and four Codex passes — and every blocker from rounds 1-3 is absorbed. Round 4's findings are absorbed except where noted inline.
>
> A ground-up redesign of the identity model is under consideration; if that proceeds, most of Release C is superseded. **Release A is worth shipping regardless** — it is non-destructive, depends on nothing else, and repairs a reconciliation path that is currently dead.
>
> Companion documents: [RCA](../rca/20260920-display-id-ownership.md) · [design](./2026-09-20-display-id-ownership-design.md) · [live schema](../entity-schema.html)

**Not estimated.** Re-derive after Release B.

## Conventions

- **Verify must discriminate.** A check that passes on today's tree is not a check. Where a proof is stateful, the fixture is rebuilt every run.
- **Status writes go through `append_phase_event()`.** Direct `UPDATE` of `status` / `workflow_phase` is caught by the `check_status_write_path` doctor check. This binds T2's archival.
- **Snapshots use `.backup`, never `cp`** — the DB is in WAL mode (`database.py:10477`).

```bash
sqlite3 ~/.claude/pd/entities/entities.db ".backup '/tmp/pd-pre-structural.db'"
sqlite3 /tmp/pd-pre-structural.db "PRAGMA integrity_check; SELECT COUNT(*) FROM entities;"
```

---

# Release A — non-destructive reconciliation fix (ships alone, first)

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

**Verify.** For every bucket, `next_val > max(parsed legacy seq, display seq)`. Assert on **all six workspaces**, not just this one. Re-run returns an unchanged mapping.

**Depends.** Nothing.

## B5 — Select the archival set

**Contract.** A pure, re-runnable selector returns exactly the entities to archive. Selection is **by the archival marker's absence**, not by terminal status — 168 of the 180 rows were already terminal, so status cannot distinguish "archived by the break" from "already dropped". Returns 180 before B6 and 0 after.

**Interface.** `select_legacy_entities(conn) -> list[LegacyRow]`, `LegacyRow = (uuid, kind, entity_id, status)`. No writes.

**Verify.** Returns 166 backlog + 3 brainstorm + 1 feature + 10 project. After B6, returns 0 — this is the idempotence proof and it fails today.

**Depends.** B4.

## B6 — Archive durably, and make it stick

**Contract.** Every selected entity carries a durable archival marker, retains its row, uuid, history and parent links, and keeps its `entity_id` unchanged. No number is freed. Reconciliation does not revert it.

**Interface.**
- Marker: a dedicated field (tag or metadata key), **not** status alone.
- Status write, where used, goes through the real signature — `append_phase_event(*, type_id, project_id, event_type="entity_status_changed", workspace_uuid, metadata={"new_status": ...})` (`database.py:9153`), which applies `metadata["new_status"]` at `:9302`. *(The earlier draft's `entity_uuid=/axis=/to_value=` kwargs were invented and do not exist.)*
- **Reconciliation authority:** `_sync_meta_json_entities` writes `.meta.json` status back over the entity when they differ (`entity_status.py:84-88`), so archival is reverted at the next session start for any entity whose artifact survives — every legacy project. Either retire the artifact or make the marker take precedence.

**Note:** the lifecycle machine does *not* permit these transitions — `MACHINE_REGISTRY['backlog'].validate('open','archived')` returns `allowed=False`, and `project` has no `archived` phase at all. `append_phase_event` does not consult the machine (validation lives at `router.py:452`), which is how 26 backlog rows are already `archived`. B6 therefore needs an explicit archival policy, not an assumed legal transition.

**Verify.** Assert the **selected uuids'** resulting marker state, the expected events, unchanged `entity_id` values, and a clean second run. Integrity checks and unchanged parent counts all pass if archival does nothing — they are necessary, not sufficient. Then run reconciliation and assert the marker survived.

**Depends.** B5.

## B7 — Exclude archived from live projections

**Contract.** Marked entities do not appear in the Kanban board, `backlog.md`, or list tools. Their numbers remain reserved by the counter.

**Interface.** Status/marker filters in the projection writers. **No change** to C1's census.

**Verify.** `backlog.md` shows only live items. The reservation assertion belongs to B4 and is checked there — not deferred to C1, which depends on B6 and would make this a forward dependency.

**Depends.** B6.

---

# Release C — atomic cutover (C1–C21 ship together)

**T3 before T4** leaves a build where an old non-strict write creates an entity without a display row (`database.py:7435`), the completeness guard correctly refuses, and allocation stops. **T4 before C15** reopens the duplicate project-identity window. **T4 before C18** leaves the startup producer minting non-canonical ids. Release C must also name how long-lived MCP processes and session hooks from an older build are prevented from writing during and after cutover.

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

**Contract.** Allocation refuses when its bucket has **non-archived** entities lacking display rows. Archived legacy rows neither satisfy nor violate the guard — scoping it to all entities would refuse every bucket the clean break touches, including the ones B6's replacements need. An empty bucket is complete. No census maximum means zero; an absent counter starts at one. The check examines existing entities, never the pending allocation. Failure rolls back **without advancing the counter**. Repair happens outside the transaction — no recursive migration or registration while holding the write lock.

**Interface.** Private helper called inside the existing `BEGIN IMMEDIATE` (`:10261`); raises a typed error.

**Verify.** Fresh DB allocates `1` (empty bucket is complete). A bucket with one display-less entity refuses **and** leaves `sequences.next_val` unchanged — assert the counter, not just the exception.

**Depends.** C2.

## C4 — Single display-id renderer

**Contract.** Exactly one function converts `(kind, seq, slug)` to a display string. Allocator and registrar cannot disagree.

**Interface.** `render_display_id(kind: str, seq: int, slug: str) -> str`. Call sites `entity_server.py:691` and `id_generator.py:68`, which independently hardcode `f"{seq:03d}-{slug}"`, both route through it.

**Verify.** AST count of executable f-strings producing `{seq:03d}` → exactly 1. A textual `grep -c` also counts documentation examples.

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

**Verify.** Full suite green; no caller constructs an `entity_id` string; upsert idempotence has its own red-first test (same identity twice → one row, status updated).

**Depends.** C5, C6.

## C8–C12 — Readers adopt their contracts

Each subtask takes one row of design D5. **Contract:** the reader returns the same output as today for valid data, sourced structurally. **Interface:** the site's own signature is unchanged; only its *source* moves, per the table below — these are five separate subtasks, one per row. **Verify:** an output-contract assertion per category — "lint green plus an artifact-path test" would pass after deleting the parsing while returning wrong fields.

| # | Need | Source | Sites |
|---|---|---|---|
| C8 | kind | `entities.kind` | `router.py:358,421`; `frontmatter_sync.py:109`; `workflow_state_server.py:1113,1395` |
| C9 | seq / slug | `entity_display(uuid)` | `frontmatter_inject.py:82`; `workflow_state_server.py:485,675` |
| C10 | parent kind + **opaque** identity | `parent_uuid` → parent row → `kind` + stored `entity_id` (design D9); parent *display* only when present | `frontmatter_inject.py:103`; `frontmatter_sync.py:125` |
| C11 | artifact path | `entities.artifact_path` | `engine.py:366` + 10 callers |
| C12 | rendered width / re-kind | C4 renderer; regenerate key from columns | `workflow_state_server.py:410`; `database.py:7815` |

C8 note: `router.py:352` already fetches the entity row carrying `kind`, then splits the string three lines later. `workflow_state_server.py:452` likewise reads `entity["kind"]` and parses anyway at `:485`.

C10 note: D0 leaves three live children attached to **archived parents that have no display row**. Reading the parent's stored `entity_id` opaquely (as `frontmatter_inject.py:90` does today) is a column read, not inference; decomposing it into seq/slug is. Add the retained-lineage fixture explicitly.

**Verify (all five):** use fixtures where the textual id **disagrees** with the structured data, and assert the structured result. Asserting unchanged output alone passes today's text-parsing readers.

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

**Depends.** C15 depends on C5; C16 depends on C15.

## C17 — One workspace identity through allocate and register

**Contract.** Allocation and registration at every production call site resolve the **same** workspace value. This is a caller-level invariant, not an enforced one: `next_sequence_value` returns a bare `int` and `register_entity` takes `seq`, `slug` and `workspace_uuid` independently, so nothing binds a number to its issuing workspace, and `entity_display` has only a uuid primary key with a non-unique seq index (`database.py:4168`). An adversarial cross-workspace registration therefore cannot be made to fail without allocation provenance — which is out of scope here.

**Interface.** `task_promotion.py:354` (allocate) and `:374` (register); `entity_server.py:839` and `:857`.

**Verify.** Assert both call sites pass one resolved workspace value through allocate and register — a caller-level regression test, not a rejection test.

**Depends.** C2.

## C18 — Canonicalize the startup backfill

**Contract.** `run_backfill` produces canonical identities or nothing. It cannot mint bare `P{NNN}`.

**Interface.** `backfill.py:566` (upsert) and `:511` (lookup omitting the slug); invoked at `entity_server.py:273`.

**Verify.** Two halves — "no bare-`P` row" passes if imports are silently disabled. (a) positive: a canonical import produces a canonical row; (b) negative: a legacy `.meta.json` produces no bare-`P` row **and** an explicit skip diagnostic.

**Depends.** C5.

## C19–C20 — Rebuild seeds from structure

**C19 Contract.** Rebuild carries structured display data through the uuid remap instead of re-parsing. **Interface:** `rebuild_tool.py:615`, `:1107`. **Verify:** a rebuild of a DB containing `P{NNN}-{slug}` preserves `seq`/`slug` exactly.

**C20 Contract.** Seeding preserves the stored high-water mark rather than deriving solely from entity rows (`:1044`) — monotonicity depends on it. **Interface:** `_seed_sequences` (`:1045`, `:1051`). **Verify:** rebuild a DB whose counter exceeds its census max, **and** a bucket with a counter but zero entity rows — rebuild enumerates buckets from entities (`rebuild_tool.py:1044`), so a counter-only bucket is the case that silently loses its reservation. Assert neither counter is lowered.

**Depends.** C19 depends on C1; C20 depends on C19.

## C22 — Recreate the live remainder

**Contract.** The 6 open backlog items and ~3 live projects exist in the new shape with fresh uuids, display rows, and **newly issued** numbers. No recreated entity reuses an archived entity's number.

**Interface.** Ordinary creation paths only (`/pd:add-to-backlog`, project creation) — through the *new* writer. No bespoke insert.

**Verify.** Each new entity has an `entity_display` row; every issued `seq` exceeds the bucket's pre-break high-water mark recorded by B4; the 3 live children remain attached to their archived parents.

**Depends.** C5, C7, C15–C16. *(This was Release B's recreate step. It cannot close inside Release B — recreating through the new writer requires the cutover, so "all of B closes before C" was never achievable.)*


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

**Depends.** C6, C7, C8–C12, C13, C14, C15–C16, C17, C18, C19–C20, C22. *(Not "all of Release C", which included itself.)*

---

## Sequencing

The explicit `Depends` lines are authoritative; this diagram is derived from them.

```
Release A   A1 ── A2 ── A3

Release B   B1 ── B2 ── B3
            B4 ── B5 ── B6 ── B7

Release C   C1 ─┬─ C2 ─┬─ C3
                │      ├─ C14 ─┐
                │      └─ C17 ─┤
                └─ C19 ── C20 ─┤
            C4 ── C5 ─┬─ C6 ── C7 ─┬─ C22 ─┤
                      ├─ C8–C12 ───┤       ├─ C21
                      ├─ C13 ──────┤       │
                      ├─ C15–C16 ──┤       │
                      └─ C18 ──────┴───────┘
```

## Out of scope

- The 22 historical duplicate feature numbers. Inert; repair would rename live directories and branches.
- Resolving #081 (hard delete vs append-only history). A1–A3 explicitly do not touch it.
- The v2 `sequences` shape divergence (RCA S8) — no live importer.

## Risks

- **B5 is a data migration on a shared multi-project DB.** `.backup` first, integrity checks after, recount all five other workspaces.
- **B7 and C1 pull in opposite directions** — archived rows are hidden from projections but must remain in the census. Assert both; do not "simplify" later.
- **C5 and C7 must land together.** The largest single unit; rehearse on a copy.
- **Ordering violations are silent.** Release C before B leaves an under-populated census; monotonic `max(stored, …)` limits the damage but does not license skipping the order.
