# Spec: 132-backfill-rebuild-tool

P004 FR-12 + Migration Path (prd.md:90,140-142) — the cutover feature every prior cluster deferred into. Sources: roadmap.md:49 (entry 15, incl. the 122-moved derive_kanban deletion), backlog #054 (three cutover decisions), #055/#060 (fix-forward mandate: acknowledged-but-lost writes die here), #062, #067 (perf obligation), #068, 127's GO artifact (docs/features/127-db-sole-truth-guard-rewire/db-read-latency-verification.md), 124 seams (schema_v2.py:64 comment, depends_on_features materialization), 125/123 handoffs (LEGACY_VALUE_REMAP deletion, ui/routes/helpers.py:144).

## Scope model (load-bearing)

The new DB file is born from ONE canonical all-DDL bootstrap: the current operational DDL (entities, workspaces, entity_relations, workflow_phases, phase_events, sequences, FTS) ∪ the v2 event core (schema_v2.py: events + entity_axis_state/entity_state views + _metadata) ∪ 122's vocabulary triggers ACTIVE from birth (roadmap:49 "reconcile 120/126's dark-suite arbitrary-value writes against the then-registered 122 vocab triggers"). Existing v1 access-layer code keeps working against the new file; the events path becomes live; per-consumer rewires beyond this spec's deletion inventory are NOT in scope (133 owns doctor; later work owns full v1-path retirement). The old file is retained read-only for 30 days as the escape hatch.

## Functional Requirements

- **FR132-1 (rebuild tool):** A committed, idempotently re-runnable tool stands up a NEW DB file at a path distinct from `~/.claude/pd/entities/entities.db`, via the canonical all-DDL bootstrap seeded from `bootstrap_v2` (schema_v2.py:130) extended per the Scope model. Schema version lives in ONE location (`_metadata.schema_version`, reset to the v2 counter — schema_v2.py:16); the v1 `MIGRATIONS` chain does not apply to the new file (fingerprint: no `schema_version` row shaped like v1's, no migration table entries). #062 lands here: the `schema_version` write becomes upsert (ON CONFLICT DO UPDATE), with a version-bump re-bootstrap test.
- **FR132-2 (backfill by replay):** The tool imports the live census (533 entities / 7 workspaces at PRD time — re-count at run) from the old file: every entity → an `entity_created` event + projection rows; every `phase_events` row → an event mapped onto the two axes; `status`/kanban derived ONCE at import via the current `derive_kanban` logic (prd.md:142), then that logic is deleted (FR132-5). Identity: fresh UUIDv7 minted per entity (PRD Migration Path); ALL uuid references (parent_uuid, entity_relations.from/to_uuid incl. 124's blocks edges, events.entity_uuid, workflow rows) remap through one old→new mapping applied atomically; the old uuid is preserved in the entity_created payload. Malformed legacy rows (empty ids, duplicate P001s) are deduped/normalized and LISTED in the report, never silently skipped (prd.md:106).
- **FR132-3 (checksum/anomaly report):** Import emits a committed report artifact: counts per kind × workspace (old vs new, with equality or explained delta), dedupes performed, normalizations, orphans, uuid remap count, and a content checksum over a canonical serialization of both sides' comparable fields. Non-zero unexplained delta = tool exits non-zero.
- **FR132-4 (cutover):** After a successful backfill+report, the standard resolution path (`ENTITY_DB_PATH` default) points at the new file. Session-start reads use the per-entity `entity_axis_state` primitive per 127's GO (predicate pushes down; the pivoted `entity_state` full-view stays for full-table reads only — #067 measured per-entity pivot reads O(total events)). The GO's precondition is satisfied in-spec: latest-event-per-axis semantics are pinned BEFORE cutover (fresh uuid7 event ids are time-ordered; define and test the tie-break within one millisecond). Post-cutover mutation writes append events + projection in ONE `BEGIN IMMEDIATE` (NFR-1); success is reported only AFTER commit — closing the #055/#060 acknowledged-but-lost class, each pinned by a regression test shaped on its incident (backlog registration visible to get_entity + raw SQL immediately after success; phase_events row exists after complete_phase reports success).
- **FR132-5 (deletion inventory — all in this feature, post-backfill):**
  (a) `derive_kanban` (workflow_engine/kanban.py:25) + its SIX call sites: workflow_state_server.py:1003/:1272, backfill.py:335, reconciliation.py:201, feature_lifecycle.py:205, engine.py:529 — each rewired to read the stored two-axis columns; comment/docstring stragglers swept (axes.py:70, constants.py:4, router.py:70, board.py:28 + import lines).
  (b) Migration-11 shims: the `_atomic_write_workspace_mapping` writer (database.py:1726 — also closes #066's root cause) and entity_server.py's legacy `project_id` kwarg surface (grep-enumerate at design; roadmap's :551 anchor has drifted).
  (c) `LEGACY_VALUE_REMAP` (ui/routes/helpers.py:144) — deletable because backfill normalizes stored values to the 122 vocab (125 handoff: remap deletes at 132's backfill).
  (d) #054(c): `create-project.md` P{NNN} filesystem scan → atomic allocator; backfill seeds v2 `sequences` for EVERY kind from the census max; remove `allocate_entity_id`'s `entity_type="project"` rejection guard in the same change.
- **FR132-6 (old-DB window):** The old file is made read-only (chmod + a doctor-visible marker recording the cutover date and the 30-day expiry); the tool never deletes it. Any code path that would WRITE the old path post-cutover fails loud.
- **FR132-7 (#068):** The new file's events immutability holds against `INSERT OR REPLACE` (enable `recursive_triggers` on connect to the new file, or a BEFORE INSERT uuid-collision guard trigger — design chooses), with a teeth test proving REPLACE cannot silently delete+reinsert an event.

## #054 decisions pinned (a/b resolved here, not deferred)

- **(a) dropped-UNIQUE reliance:** v2 `entities` has no UNIQUE on `type_id` (schema_v2.py:43-58 carries composite workspace scoping per 109/129); consumers that leaned on v17 uniqueness must be enumerated at design from the CALL GRAPH of `resolve_entity_uuid`/`get_entity`-by-type_id (per #078), and each must tolerate duplicates via workspace scope or newest-wins with a warning.
- **(b) mixed uuid4/uuid7:** re-mint ALL entities as uuid7 at import (PRD Migration Path "fresh UUIDv7s"); no grandfathering — one identity generation, old uuid in payload for lineage.

## Success Criteria

- **SC1:** Fresh-bootstrap test: tool creates the new file from an empty state; `_metadata.schema_version` is the ONLY version cell (grep the new-file writer set for any second version write — #062's upsert test included); 122 vocab triggers fire on the new file from birth (arbitrary-value INSERT rejected).
- **SC2:** Backfill parity: on a seeded corpus modeling the live census's pathologies (empty ids, duplicate P001s, uuid4 rows, blocks edges, multi-workspace), the report shows per-kind×workspace equality (or enumerated deltas), every anomaly listed, checksum stable across two runs (idempotence: second run no-ops or reproduces byte-identical report).
- **SC3:** Replay property (prd.md:107): for every imported entity, replaying its event stream reproduces the projection field-by-field; divergence fails the test naming the entity and field.
- **SC4:** Cutover reads: session-start resolver reads the new file via per-entity `entity_axis_state`; p95 ≤ the 127-recorded 31ms walk baseline at the 533-entity census (re-run 127's committed harness against the new file); EXPLAIN shows the predicate pushdown, not a full-view scan.
- **SC5:** Deletion grep-gate: zero live references to `derive_kanban`, `_atomic_write_workspace_mapping`, `LEGACY_VALUE_REMAP`, and the legacy `project_id` kwarg outside git history/migration-frozen code/this feature's artifacts (exemption list pinned at design — #077 discipline: any NEW value the backfill writes into a CHECK/trigger-constrained column is grepped against the live constraint definition first).
- **SC6:** Old-DB safety: post-cutover, a write attempt against the old path fails loud (test); the read-only marker carries the dated expiry.
- **SC7:** #055/#060 regression pins green (FR132-4's two tests) — the write path cannot report success before commit.

## Hazards

- **H1 (FK remap atomicity):** re-minting uuids while 124's blocks edges + parent_uuid webs reference the old ones — the remap must be one transaction over the whole import; a partial remap is worse than no rebuild. SC2's idempotence run doubles as the torn-import probe.
- **H2 (CHECK/trigger collisions at import — the #077 class):** backfilled values (legacy statuses, v1 phase names, `cascade_ready`, 5D phases) must be grepped against EVERY constraint the canonical bootstrap registers (122 triggers, event CHECKs incl. 119's vocab, entity_relations kind CHECK) before the import runs. The old DB contains 10 live status values incl. 13 empty-string rows (PRD evidence).
- **H3 (MCP startup caching):** servers cache DB path + workspace uuid at startup (prd.md:119; live-demonstrated by 124's stale-server incident) — cutover REQUIRES a session restart; the tool must print this loudly and the doctor marker must make a stale-path server detectable.
- **H4 (dark-suite reconciliation):** 120/126 test suites write arbitrary axis values that 122's now-active triggers reject — those fixtures move to vocabulary-legal values in the same change (roadmap:49); expect suite churn, bounded by the trigger vocabulary.
- **H5 (hooks/lib self-reference):** session-start hooks load database.py against whatever file exists — during the implementation window the repo's own session hooks run pre-cutover code; mirror 124's live-DB discipline (tool runs only when invoked, never at import time of the module).
- **H6 (#059 adjacency):** the fork-race flake lives in the OLD migration chain's tests; do not let new-file tests share its fixture pattern.

## Non-goals

Doctor check retirement (133); full v1 access-layer retirement beyond the deletion inventory (later work — the events path is live but v1 readers stay); workflow-rebuild track items (#057/#058, secretary, YOLO consolidation); #064 sentinel label (backfill dedupe may moot it — verify at QA, do not build); #069/#070 (separate owners); old-DB deletion (manual, after the window); express-mode phase-subset representation (PRD OQ-6, workflow track).

## Open Questions (design phase resolves)

- **OQ-1:** New file path/name (`entities-v2.db` beside the old vs a versioned dir) and how `ENTITY_DB_PATH` default flips — env-var precedence must keep tests hermetic.
- **OQ-2:** Whether `entities_fts` rebuilds at import or lazily on first search on the new file.
- **OQ-3:** Report artifact home (`docs/projects/P004-entity-db-redesign/` vs `~/.claude/pd/migrations/`) — it contains live-DB census data; repo placement must not leak private entity names into git if the repo ever publishes.
