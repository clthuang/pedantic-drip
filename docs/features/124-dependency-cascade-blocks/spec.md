# Spec: 124-dependency-cascade-blocks

**Source:** P004 FR-8 (prd.md:86) — cluster 3. **Depends on:** 123 (shipped — router owns per-kind transitions). **Consumed by:** 132 (backfill replays blocks rows; physical cutover).
**Goal:** ONE dependency store — `entity_relations(kind='blocks')` — replacing today's three representations, plus the completion cascade: when a blocker resolves, downstream entities whose blockers are ALL resolved flip `execution_status blocked → ready` via a recorded follow-on event.

## Survey (live tree, 2026-07-13, develop 26f8b712)

Three dependency representations coexist today:

1. **`entity_dependencies` table** (v1 bootstrap step 7, database.py:872-887: `(entity_uuid, blocked_by_uuid)` UNIQUE pair + 2 indices — no kind, no FK, no timestamps). The LIVE mechanism: `dependencies.py` (dep_mgr) with recursive-CTE cycle guard (database.py:9215-9240, max_depth bounded); MCP `add_dependency`/`remove_dependency` (entity_server.py:406-431, refs resolved :1261/:1299); doctor checks — blocked-entity lookup (checks.py:1146), orphan-edge (checks.py:1791), stale-edge-to-completed (checks.py:1861-1881).
2. **`depends_on_features` metadata JSON list** — written by the decomposing skill at project creation; validated (metadata.py:42); read by yolo_deps.py:35 (YOLO dependency gate), server_helpers.py:71 (display), backfill.py:573-574.
3. **`entity_relations`** (migration 14, feature 111) — `kind TEXT NOT NULL CHECK(kind IN ('fixes'))` (database.py:4962) + 3 indices; sole consumer today is `complete_phase(closes=[])` fixes linkage.

**Not found:** `_cascade_unblock` has NO live definition — `git log -S` locates it only in docs (052-reactive-entity-consistency design.md:102, a designed-never-shipped feature, plus the P004 PRD/brainstorm restating it). The cascade is NEW code, not a re-home.

`ready` is already in `EXECUTION_STATUSES` (axes.py:75, inserted by 122 explicitly as "PRD FR-8's blocked → ready cascade target, feature 124") — no vocabulary change in this feature.

## Functional Requirements

- **FR124-1 (kind widening):** `entity_relations.kind` CHECK widens to `('fixes','blocks')`. SQLite CHECKs are immutable → copy-rename table rebuild following the migration-14 pattern (BEGIN IMMEDIATE, `PRAGMA foreign_key_check` pre-commit, replay-safe early-return, `PRAGMA table_info` column discovery — CLAUDE.md SQLite migration patterns).
- **FR124-2 (single store — table unification):** `entity_dependencies` rows migrate to `entity_relations(kind='blocks', source_uuid=blocker, target_uuid=blocked)` (column mapping pinned at design). All consumers rewire: dep_mgr add/remove/query + the cycle-guard CTE, both MCP tools (surface contract unchanged — same params, same result strings), and the three doctor checks. The `entity_dependencies` table is then DROPPED (no back-compat, repo principle). Orphan edges (either uuid unresolvable) are dropped at migration with a per-row stderr note, mirroring the doctor orphan-edge check's definition.
- **FR124-3 (metadata migration):** `depends_on_features` metadata entries materialize as `blocks` rows at migration time (ref-resolved; unresolvable refs skipped with a note, metadata left intact for audit). Post-migration, registration paths that WRITE `depends_on_features` also write the relation row; readers (yolo_deps.py:35, server_helpers.py:71) rewire to query relations. The metadata key itself is not deleted (132's backfill decides final disposition).
- **FR124-4 (completion cascade):** When a blocker entity reaches its completion state, every downstream entity (via `blocks` rows) whose blockers are now ALL resolved AND whose current `execution_status` is `blocked` flips to `ready` via a follow-on recorded event in the SAME `BEGIN IMMEDIATE` transaction as the triggering write (NFR-1). Only `blocked → ready` — a downstream entity in any other execution status is untouched. Idempotent: re-completing a blocker or replaying the event produces no duplicate flips (guard: only-if-currently-blocked).
- **FR124-5 (completion predicate, per-kind):** "Blocker resolved" = the blocker's execution axis reaching `completed` (or the entity's kind-terminal equivalent — exact per-kind predicate table pinned at design using 123's `MACHINE_REGISTRY` descriptors; feature kind: finish-phase completion). The predicate must be a single named helper, not inline duplicates.

## Success Criteria

- **SC1:** The widened CHECK admits `blocks` and still rejects unknown kinds (insert probes both directions); migration is replay-safe (second run = no-op) and passes `PRAGMA foreign_key_check`.
- **SC2:** Migration parity: every pre-migration `entity_dependencies` row and every resolvable `depends_on_features` edge has exactly one post-migration `blocks` row (count + spot-check assertions); `entity_dependencies` table ABSENT post-migration (`sqlite_master` probe); orphans logged not silently dropped.
- **SC3 (cascade end-to-end, red-first):** Seed A blocks B (B `blocked`): completing A flips B to `ready` + appends the follow-on event row (actor recorded). Seed A,C both block B: completing A leaves B `blocked` (event NOT appended); completing C then flips B. Seed B at `wip`: completing A does NOT touch B.
- **SC4:** Cycle guard preserved: `add_dependency` still rejects cycles on the new store (CTE ported; same rejection contract as database.py:9215).
- **SC5:** The three doctor checks query `entity_relations(kind='blocks')`; the stale-edge check's semantics update — an edge to a completed blocker with downstream still `blocked` is now a MISSED-CASCADE finding (fix action: run the cascade), not merely stale.
- **SC6:** `grep -rn "entity_dependencies" plugins/pd/ --include="*.py"` → zero non-test survivors (tests may reference it only in migration tests seeding the OLD shape).

## Survey Hazard Dispositions

| # | Hazard | Disposition |
|---|---|---|
| H1 | PRD FR-8's "re-homes F052's `_cascade_unblock`" — function never shipped (052 design.md:102 only) | Cascade is NEW code. F052's design consulted as prior art only. PRD restated-literal noted, not propagated. |
| H2 | PRD says "blocked_by metadata JSON array"; the live store is the `entity_dependencies` TABLE (+ `depends_on_features` metadata) | Spec enumerates all three representations (Survey); FR124-2/-3 cover both live stores. |
| H3 | SQLite CHECK immutability | Copy-rename rebuild per migration-14 pattern (FR124-1). |
| H4 | v1-live vs v2-dark write-path split: live execution-status writes go through workflow_phases/kanban_column until 132's cutover; v2 `events` is dark | Cascade hooks the LIVE post-123 write path; the recorded "follow-on event" uses the same event convention that path uses today. Exact hook point = design D-item (candidates: router-adjacent in entity_engine/engine completion paths). NOT a new parallel writer. |
| H5 | `query_ready_tasks`/`promote_task` MCP tools already exist — semantics of `ready` there may predate the cascade | Design-phase verification item: enumerate their readiness derivation before wiring; they must consume, not contradict, cascade-set `ready`. |
| H6 | Doctor stale-edge check (checks.py:1861) treats edges-to-completed as findings — post-cascade these should be impossible unless the cascade was missed | SC5 updates the check's meaning + fix action. |
| H7 | `entity_relations` has no `UNIQUE(kind, source, target)` today (fixes rows unconstrained) | Design decides: add the composite UNIQUE in the same rebuild (cheap while the table is being copied) — required for SC2 exactly-one parity. |

## Open Questions (design phase)

- **OQ-1:** Per-kind completion predicate table — which of the 8 router kinds can BE blockers, and what is each kind's terminal (`completed` execution status vs lifecycle terminal `promoted`/`archived` vs feature finish)? (MACHINE_REGISTRY descriptors are the source.)
- **OQ-2:** Cascade event `actor` value (`system:cascade` vs the completing actor) — NFR-4 requires it recorded; PRD OQ-2 owns the vocabulary.
- **OQ-3:** Do `blocks` rows survive blocker completion (audit trail, doctor-visible) or get tombstoned? Lean: survive — events are the audit, rows are current-state; the cascade only reads unresolved ones.

## Out of Scope

- Physical `kanban_column → execution_status` rename, LEGACY_VALUE_REMAP deletion, v2 cutover/backfill (132).
- UI rendering of `ready` (shipped at 125; column already ordered third).
- New concurrency machinery (NFR-1 reuses `sqlite_retry` + BEGIN IMMEDIATE).
- `depends_on_features` metadata key deletion (132's backfill decides).
