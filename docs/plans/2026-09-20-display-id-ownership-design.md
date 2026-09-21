# Structural Identity — Design

**RCA:** [docs/rca/20260920-display-id-ownership.md](../rca/20260920-display-id-ownership.md)
**Date:** 2026-09-20 (rev 3 — clean break; supersedes the in-place-migration design)

> **Status — preserved.** Design for the system as it stands on 2026-09-20. Revised three times under adversarial review; rev 1 (a parser module) and rev 2 (in-place backfill) were both withdrawn and the reasons are recorded inline, since they are the most useful part of the document if a ground-up redesign follows.

## Governing rules

1. **A human-readable id is for humans to read.** No code infers anything from it.
2. **Kind and inter-entity relationships come from data structure**, never from parsing text.
3. **Sequences are monotonic and never recycled.** A number, once issued, is never issued again — not after abandonment, not after archival, not ever. Gaps are normal and carry no meaning.

Rules 1 and 2 are the user's. Rule 3 is what makes the clean break safe.

## Overview

Every structure these rules require already exists in the schema — `entity_display(uuid, seq, slug)`, `entities.kind`, `entities.artifact_path`, and uuid-keyed `parent_uuid` / `entity_relations`. Feature 110 already declared the invariant ("entity_id parsing only happens in `_migration_13_*` functions and test files", `database.py:10148`) and built the table to serve it. The migration was never finished, and the lint meant to enforce it cannot detect any real parsing idiom (RCA).

Rev 2 tried to finish that migration in place: backfill 180 legacy rows correctly, activate a v2 migration that would not otherwise run, preserve legacy key spellings, and hold completeness across a mixed-writer window. That was the bulk of the risk and all of the blocking complexity.

**Rev 3 abandons in-place repair.** Legacy entities are archived where they stand; the small live remainder is recreated in the new shape. What remains is a code change, not a data migration.

## D0 — The clean break

**Archive, do not convert.** Entities without structural identity keep their rows, uuids and history, are marked archived durably, and are excluded from live projections. Nothing is rewritten in place.

Three properties status alone does not provide, and which D0 therefore requires explicitly:

- **A durable archival marker distinct from status.** 168 of the 180 rows are *already* terminal, so "has a terminal status" cannot distinguish "archived by the clean break" from "was already dropped". Without a distinct marker the operation is neither idempotent nor auditable.
- **Authority over reconciliation.** `_sync_meta_json_entities` writes `.meta.json` status back over the entity when they differ (`entity_status.py:84-88`), so archival will be reverted at the next session start for any entity whose artifact survives — which includes every legacy project. Archival must either retire the artifact or take precedence.
- **Selection that is stable across runs.** "Missing display row" selects the same 180 rows before and after the operation; "terminal status" selected 168 of them beforehand. The predicate must be the marker, so a second run selects zero.

Measured scope:

"Terminal" below means production's own `TERMINAL_STATUSES = {promoted, abandoned, archived}` (`entity_status.py:10`). **NULL is not terminal** — an earlier revision of this table counted it as such, which is how brainstorm and feature reported "0 to recreate".

| Kind | Legacy rows | Already terminal | To recreate | Outside this workspace |
|---|---|---|---|---|
| backlog | 166 | 160 | 6 (all LOW test-gap/lint items) | — |
| brainstorm | 3 | 2 | 1 (NULL status) | `cast-below`: `original-ideation-prd` |
| feature | 1 | 0 | 1 (NULL status) | `/Users/terry_agent`: `unnamed-b43fd0f1` |
| project | 10 | 3 | 7 non-terminal rows | `/Users/terry_agent`: `P001` + `P001-agent-orchestrator`, both **active** |

Three of the project rows are duplicate *pairs* of the same project (`P002`/`P002-memory-flywheel`, `P003`/`P003-entity-system-redesign`, `P001`/`P001-agent-orchestrator`) — not "bare-`P` duplicates" of a canonical row, since `/Users/terry_agent`'s pair is slug-form on both halves. Children are split across both halves of each pair, so which half is authoritative is an open decision, not a detail.

**Cross-workspace rows are a release blocker, not a footnote.** The recreate step uses ordinary creation commands, which run in the current project's context; nothing recreates another repo's entities.

Lineage survives untouched: `parent_uuid` is a uuid foreign key, so archiving a parent is a status change, not a removal. Of 79 entities with legacy parents, 75 are themselves terminal; the **4** live children stay attached to their archived originals, which remains historically truthful.

**Archival is the only available operation anyway.** `delete_entity` cannot succeed for *any* entity — all 579 carry `events` rows under a `NOT NULL REFERENCES entities(uuid)` constraint with no `ON DELETE` clause (backlog #081, recorded at `database.py:8537-8543`). An append-only event core makes archive-not-delete native rather than a compromise.

## D1 — Identity is read, not derived

No parser module. Callers needing seq/slug call `get_entity_display(uuid)` (`database.py:10307`); needing kind, read `entities.kind`; needing a path, read `artifact_path`. `entity_id` remains a stored, human-facing string that nothing parses.

## D2 — The allocator is monotonic by construction

```sql
SELECT MAX(d.seq) FROM entities e
  JOIN entity_display d ON d.uuid = e.uuid
 WHERE e.kind = ? AND e.workspace_uuid = ?
```

and the issued value is `max(stored_next_val, census_max + 1)`, inside the `BEGIN IMMEDIATE` already held (`database.py:10215`, lock at `:10261`).

**The stored counter is the authority; the census is only a repair floor.** `max()` can raise the counter, never lower it — so monotonicity holds by construction, and no census result, stale row, restored backup, or archival sweep can walk a number backwards.

**Reservation is separate from display identity** — this is the correction that makes D0 work. Rev 3 first claimed "archived rows stay in the census so the floor cannot drop". That is impossible: the census is an inner join on `entity_display`, and legacy rows lack exactly that row. Under the clean break they are invisible to the census by construction, and a completeness guard that refuses display-less buckets would refuse *every* affected bucket — including the ones D0's own replacements need.

The resolution:

- **The `sequences` counter is the sole reservation authority.** It alone guarantees a number is never reissued. The census is a *repair floor* for display-bearing rows, not the record of what has been used.
- **A one-time high-water establishment (D0a) precedes the break.** Each bucket's `next_val` is raised above its true maximum *including legacy rows*. This is the only sanctioned parse of legacy ids, performed once at the migration boundary and never again.
- **The completeness guard scopes to non-archived entities.** Archived legacy rows neither satisfy nor violate it; their numbers are held by the counter.
- **Gaps are expected.** Abandoned allocations, archived entities and failed registrations all leave holes. A gap is not a defect and must never be "reclaimed".

**Recovery boundary.** Monotonicity holds while the counter is preserved. Restoring a backup that predates a set of allocations restores both counter and entities, and `max(stored, census+1)` cannot recover information absent from both — the rule is "never recycled while the high-water authority survives", not "never recycled under arbitrary rollback".

This is shape-agnostic by construction: `P004-entity-db-redesign`, `00277` and `134-workflow-rebuild` all count correctly, because `seq` is a column rather than a substring.

## D3 — Registration takes seq and slug as data

`register_entity` accepts `seq` and `slug`, writes the `entity_display` row from them, and derives the stored `entity_id` for display. Deleted: `_ENTITY_ID_FORMAT_RE` (`database.py:3960`), its gate (`:7302`), and **the second parser at `:7436-7438`** — which today builds the display row via `int(entity_id[:dash_idx])` and only `if strict:`, which is why the project bypass silently skipped creating structural identity for 10 of 12 projects.

The two existing formatters that hardcode `f"{seq:03d}-{slug}"` (`entity_server.py:691`, `id_generator.py:68`) route through the same derivation, or allocator and registrar will disagree about what an id looks like.

**No deprecated alias.** Callers migrate atomically. A helper called by ordinary registration is runtime parsing whatever it is named, and the audit approves any function prefixed `_migration_13_` (`test_audit_writes.py:542`) — an alias would build an enforcement bypass by construction, and contradicts this repo's no-compatibility-shims rule.

## D4 — Paths come from `artifact_path`

`_extract_slug` (`engine.py:366`) and its 10 callers read `artifact_path`, 100% populated for features and projects. The path-traversal check is retained as validation of the stored column.

## D5 — Per-reader contracts

Not every parse site wants kind:

| Need | Source | Sites |
|---|---|---|
| kind | `entities.kind` | `router.py:358,421`; `frontmatter_sync.py:109`; `workflow_state_server.py:1113,1395` |
| seq / slug | `entity_display(uuid)` | `frontmatter_inject.py:82`; `workflow_state_server.py:485,675` |
| parent kind *and* identity | `parent_uuid` → parent row → parent display | `frontmatter_inject.py:103`; `frontmatter_sync.py:125` |
| rendered width / prefix | rendering policy; never recovered from text | `workflow_state_server.py:410` |
| business key on re-kind | regenerate from `kind` + `entity_id` columns | `database.py:7815` |
| missing parent (no row exists) | see D8 | `backfill.py:752` |

`router.py:352` is the sharpest case: it already fetches the entity row — which carries `kind` — then derives `entity_type` by splitting the string three lines later. `workflow_state_server.py:452` likewise reads `entity["kind"]` and parses anyway at `:485`.

## D6 — Replace the vacuous lint

The grep-based `_AUDIT_PATTERN` (`test_audit_writes.py:480-485`) becomes an **AST** check. Measured on this codebase, no single regex suffices: a corrected pattern catches 5 of 6 known sites, over-matches 30 production lines (`_UUID_RE.match`, `_TAG_RE.match`, `_TASK_HEADING_RE.match`), and cannot reach `database.py:7436` at all, which parses by slicing.

Requirements: positive and negative fixtures; coverage of `re.match(pattern, eid)`, subscript access, `startswith("feature:")`, dash-index slicing and numeric conversion; UI templates in scope (`_card.html:4,10` sit outside `_SCAN_ROOTS`); comments and docstrings excluded (`database.py:7768` documents a split without performing one); and an explicit migration-boundary policy. Detection is a witness set, not a completeness proof, and never authorizes runtime behaviour by function-name prefix. Grace mode removed.

## D7 — (withdrawn)

Rev 2's in-place backfill of 180 display rows is replaced by D0. With it go the v2 migration-activation problem, the value-correctness-versus-presence problem, and the mixed-writer completeness window — the three issues that made it the plan's blocking task.

## D8 — Missing parent: report and defer

`backfill.py:752` cannot read `parent_uuid → parent row → parent display`, because its caller invokes it *precisely when the parent does not exist* (`:630-631`, guarded by `db.get_entity(parent_type_id) is None`, followed by synthetic registration). Assigning it a structural source is circular.

**Resolution: report and defer.** An unresolvable parent produces a diagnostic; no synthetic entity is minted from parsed text. Under D0 this is cheap — after the clean break a missing parent is a genuine error, not an expected legacy condition, so the case the synthetic path existed to serve no longer arises.

## D9 — Reading an archived parent

D0 deliberately leaves **four** live children attached to archived parents that have no display row. D5 assigns parent reads to `parent_uuid → parent row → parent display`, which those parents cannot satisfy, and D8's missing-parent policy does not apply because the parent *exists*.

**Distinguish two different needs.** Reading a parent's *stored opaque identity* (`entities.entity_id`, which frontmatter uses today at `frontmatter_inject.py:90`) is not text inference — it is reading a column. Deriving `seq`/`slug` from that identity is. Parent readers may read the stored identity opaquely; they may not decompose it. Archived parents are therefore readable, and only their structural decomposition is unavailable.

## What this resolves

- **RCA S2, S3, S5, S6** — the seeder stops being shape-blind, the gate stops rejecting projects, the bypass that skipped display-row creation is removed, and the census stops depending on id shape.
- **The `P{NNN}` question** — under D0 the legacy `P` rows are archived rather than carried forward, and new ids are minted structurally. The prefix survives only as a rendering choice, if wanted at all.
- **Prose drift guards** (`create-feature.md:18`, `create-project.md:18`) — deleted once D2 lands, along with the "drift" clauses added on 2026-09-20.

**Not resolved here:** duplicate business identity (S4). Removing the gate lets both project registration paths succeed again; that needs its own fix, including the `set_parent` ordering problem. The rebuild/import path also needs its own task — it parses independently at `rebuild_tool.py:615,1045,1051`.

## Risks

- **D0 is still a data migration**, just a far smaller one. Same discipline: `.backup` snapshot (not `cp` — the DB is in WAL mode), `PRAGMA integrity_check` and `foreign_key_check` after, and a recount of the other six workspaces holding entities (seven hold `sequences` rows; 24 workspace rows exist in total).
- **Archival must exclude from projections without excluding from the census.** These pull in opposite directions; D2 pins the resolution and it must not be "simplified" later.
- **D3 changes a public signature** used across fixtures and must land atomically — the largest single unit of work, and the main argument for rehearsing on a copy.
