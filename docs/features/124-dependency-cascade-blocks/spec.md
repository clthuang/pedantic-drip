# Spec: 124-dependency-cascade-blocks

**Source:** P004 FR-8 (prd.md:86) — cluster 3. **Depends on:** 123 (shipped — router owns per-kind transitions). **Consumed by:** 132 (backfill replays blocks rows; physical cutover).
**Goal:** ONE dependency store — `entity_relations(kind='blocks')` — replacing today's two live representations, and the shipped completion cascade MODIFIED to the two-axis model: flip target `blocked → ready` (not `planned`), edges survive as rows (not tombstoned), every flip lands as a recorded event.

## Survey (live tree, 2026-07-13, develop a32d6dd7; corrected at spec-i1)

**The cascade is SHIPPED, not new.** `DependencyManager.cascade_unblock` (dependencies.py:80-111 — F052's design C4/AC-29 lineage, shipped under the PUBLIC name; the PRD's `_cascade_unblock` literal is the design doc's private spelling) today: tombstones all edges from the completed blocker (`remove_dependencies_by_blocker`, :97), then flips downstream entities with zero remaining rows from `blocked → planned` (:106-109). Wired at FIVE live sites: entity_engine.py:537 (`_run_cascade` — "separate transaction" by design, :524), database.py:7577 (`update_entity` on `status=='completed'` — "AFTER transaction exits (TD-1)", fail-open, :7570-7579), reconciliation.py:596, reconciliation_orchestrator/dependency_freshness.py:29, doctor fix_actions/__init__.py:356. Tested (test_dependencies.py:197-236 et al.).

Dependency representations today:

1. **`entity_dependencies` table** (v1 bootstrap step 7, database.py:872-887: `(entity_uuid, blocked_by_uuid)` UNIQUE pair + 2 indices — no kind, NO FK, no timestamps). Full consumer surface: dep_mgr (dependencies.py — add/remove, `cascade_unblock` :80, `get_blockers` :113, `get_dependents` :119), DB methods (database.py — add_dependency :9101, remove_dependency :9113, remove_dependencies_by_blocker :9122, query_dependencies :9130, check_dependency_cycle :9198 recursive CTE), MCP `add_dependency`/`remove_dependency` (entity_server.py:403-432), the 5 cascade call sites above, doctor checks — blocked-entity lookup (checks.py:1146), orphan-edge (checks.py:1790-1816), stale-edge-to-completed (checks.py:1856-1885) — and the stale-dependency fix action (fix_actions/__init__.py:348-356).
2. **`depends_on_features` metadata JSON list** — written at project decomposition; validated (metadata.py:42); read by yolo_deps.py:29-53 (YOLO gate — reads `.meta.json` FILES off disk, not the DB), server_helpers.py:85 (display), backfill.py:573-574.
3. **`entity_relations`** (migration 14, feature 111) — columns `from_uuid`/`to_uuid`/`kind CHECK(kind IN ('fixes'))`/`created_at`, BOTH uuids `FOREIGN KEY ... ON DELETE CASCADE` (database.py:4958-4968), `UNIQUE INDEX idx_entity_relations_unique (from_uuid, to_uuid, kind)` (:4970-4972) + from/to indices. Sole consumer today: `complete_phase(closes=[])` fixes linkage.

`ready` is already in `EXECUTION_STATUSES` (axes.py:75, inserted by 122 explicitly for this feature) — no vocabulary change here.

## Functional Requirements

- **FR124-1 (kind widening):** `entity_relations.kind` CHECK widens to `('fixes','blocks')`. SQLite CHECKs are immutable → copy-rename table rebuild following migration 14's CHECK-widening helper pattern (database.py:4485 — BEGIN IMMEDIATE, `PRAGMA foreign_key_check` pre-commit, replay-safe early-return, `PRAGMA table_info` column discovery). The rebuild PRESERVES the existing `UNIQUE(from_uuid, to_uuid, kind)` index, both FK ON DELETE CASCADE clauses, and the from/to indices.
- **FR124-2 (single store — table unification):** `entity_dependencies` rows migrate to `entity_relations(kind='blocks', from_uuid=blocker, to_uuid=blocked)` (direction: from = the entity that blocks, matching 'fixes' from=actor convention). EVERY consumer in the Survey's item-1 list rewires: dep_mgr's full surface (incl. cascade_unblock/get_blockers/get_dependents), the 5 DB methods, both MCP tools (surface contract unchanged), the 5 cascade call sites, the three doctor checks, and the stale-dependency fix action. The `entity_dependencies` table is then DROPPED (no back-compat). Orphan edges (either uuid unresolvable — possible since the old table has no FK) are dropped at migration with a per-row stderr note. The orphan-edge doctor check (checks.py:1790) RETIRES for the new store — FKs make orphans structurally impossible.
- **FR124-3 (metadata migration):** `depends_on_features` metadata entries materialize as `blocks` rows at migration time (ref-resolved; unresolvable refs skipped with a note, metadata left intact for audit). Post-migration, registration paths that WRITE `depends_on_features` also write the relation row. server_helpers.py:85 rewires to query relations. yolo_deps.py DOES NOT rewire: it is a filesystem `.meta.json` reader inside the YOLO gate — moving it to DB queries would put DB availability/latency into that path; it stays on projection reads (FR-10 read posture) with `depends_on_features` metadata as its input until 132's cutover.
- **FR124-4 (cascade modification):** `cascade_unblock` changes in four pinned ways, keeping its name and call sites: (a) flip target `blocked → ready` (was `planned` — pre-two-axis); (b) store = `entity_relations(kind='blocks')`; (c) edges SURVIVE completion (was: tombstoned via remove_dependencies_by_blocker :97) — the resolved-predicate shifts from "zero remaining rows" to "every blocker's completion predicate satisfied" (FR124-5); (d) each flip is recorded as an event (actor per OQ-1) atomically WITH its status write — one transaction PER FLIP (NFR-1 applies within the flip). **Transaction discipline DECIDED:** the cascade stays a FOLLOW-ON after the triggering write's transaction (per the shipped TD-1 separation at entity_engine.py:524 and database.py:7572, and per FR-8's own "follow-on event" wording) — NOT merged into the trigger's transaction. The database.py:7577 fail-open site keeps fail-open (post-commit failure must not fail the committed caller) but gains a stderr warning (silent `except: pass` dies); recovery net = reconciliation layer + the SC5 doctor check. Only `blocked → ready`; other statuses untouched; idempotent (only-if-currently-blocked guard).
- **FR124-5 (completion predicate, per-kind):** "Blocker resolved" = a single named helper consulting 123's `MACHINE_REGISTRY` descriptors — per-kind terminal table pinned at design (feature: finish completion; 5D kinds: `completed` execution status; lifecycle kinds: their terminal phases). Today's inline `status == "completed"` checks (database.py:7574, cascade internals) collapse into it.

## Success Criteria

- **SC1:** The widened CHECK admits `blocks` and still rejects unknown kinds (insert probes both directions); migration replay-safe (second run no-op); `PRAGMA foreign_key_check` clean; the UNIQUE index and both FKs survive the rebuild (`PRAGMA index_list`/`foreign_key_list` assertions).
- **SC2:** Migration parity: every pre-migration `entity_dependencies` row and every resolvable `depends_on_features` edge has exactly one post-migration `blocks` row (the preserved UNIQUE index enforces at-most-one; counts assert exactly-one); `entity_dependencies` ABSENT post-migration (`sqlite_master` probe); orphans logged not silently dropped.
- **SC3 (cascade end-to-end, red-first on the CHANGED behaviors):** (a) A blocks B (B `blocked`): completing A flips B to `ready` (red-first: today flips to `planned`) + appends the flip event + the A→B row SURVIVES (red-first: today deleted). (b) A,C block B: completing A leaves B `blocked`, no event; completing C then flips. (c) B at `wip`: completing A does not touch B. (d) DELETING blocker A (not completing): FK removes the edge; B's unblock evaluation runs via the delete path (design D-item pins where) — B flips iff all remaining blockers resolved. (e) Cross-workspace: blocker in workspace Y, blocked in X — cascade flips (uuid refs are workspace-agnostic per FR-9); asserted deliberately.
- **SC4:** Cycle guard preserved on the new store: `add_dependency` rejects cycles (CTE ported from database.py:9198; self-dependency still rejected).
- **SC5:** Doctor missed-cascade check: fires ONLY when a downstream is `blocked` AND every one of its blockers satisfies the completion predicate (kills the multi-blocker partial-completion false positive of a naive edge-to-completed scan); fix action = run the cascade evaluation. The old stale-edge check (checks.py:1856) and orphan-edge check retire/replace accordingly.
- **SC6:** `grep -rn "entity_dependencies" plugins/pd/ --include="*.py"` → zero non-test survivors (tests may reference it only when seeding the OLD shape in migration tests).

## Survey Hazard Dispositions

| # | Hazard | Disposition |
|---|---|---|
| H1 | PRD FR-8's `_cascade_unblock` literal names F052's design-doc private spelling; the SHIPPED function is public `cascade_unblock` (found at spec-i1 after the draft's verbatim-literal grep missed it) | FR124-4 is a MODIFICATION of the shipped function — hook points are the 5 existing call sites, not new wiring. |
| H2 | PRD says "blocked_by metadata JSON array"; live stores are the `entity_dependencies` TABLE + `depends_on_features` metadata | Survey enumerates all; FR124-2/-3 cover both. |
| H3 | SQLite CHECK immutability | Copy-rename rebuild per the m14 CHECK-widening helper (database.py:4485), FR124-1. |
| H4 | Trigger/write-path split: live cascade keys on v1 `status=='completed'` (database.py:7574); v2 `events` is dark until 132 | FR124-5's predicate helper abstracts the terminal test; the recorded flip event follows the post-123 live event convention. No new parallel writer. |
| H5 | `query_ready_tasks`/`promote_task` MCP predate the cascade's `ready` | Design-phase verification item: enumerate their readiness derivation; they must consume, not contradict, cascade-set `ready`. |
| H6 | Behavior deltas hiding in the store swap: no-FK→FK ON DELETE CASCADE (deletion semantics, SC3-d), tombstone→survive (FR124-4c), planned→ready (FR124-4a) | Each pinned as a red-first SC3 case; deletion-path unblock evaluation is a design D-item. |
| H7 | `UNIQUE(from_uuid,to_uuid,kind)` + FKs already exist on entity_relations (database.py:4970-4972) | Rebuild PRESERVES them (SC1 asserts); nothing to add. |

## Open Questions (design phase)

- **OQ-1:** Cascade event `actor` value (`system:cascade` vs the completing actor) — NFR-4 requires it recorded; PRD OQ-2 owns the vocabulary.
- **OQ-2:** Where the blocker-DELETION unblock evaluation hooks (delete_entity path vs reconciliation-only) — SC3-d pins the observable outcome either way.

## Out of Scope

- Physical `kanban_column → execution_status` rename, LEGACY_VALUE_REMAP deletion, v2 cutover/backfill, `depends_on_features` key deletion (132).
- UI rendering of `ready` (shipped at 125).
- New concurrency machinery (NFR-1 reuses `sqlite_retry` + BEGIN IMMEDIATE per flip).
- Reworking the reconciliation/doctor layered-recovery architecture (kept as the cascade's net, per TD-1).
