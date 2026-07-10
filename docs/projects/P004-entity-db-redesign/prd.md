# PRD: Entity DB Redesign — Single-Truth, Event-Sourced, Multi-Workspace

## Status
- Created: 2026-07-10
- Last updated: 2026-07-10
- Status: Draft
- Problem Type: none
- Archetype: improving-existing-work
- Entity: `brainstorm:20260710-153600-entity-db-redesign`
- Track: 2 of 2 (companion: `20260710-153500-workflow-rebuild.prd.md`) — **this track ships first**

## Problem Statement

pd's entity data model generates its own fragility: identity is split across two join keys, the human-readable business key is allocated racily and collides across workspaces, authoring-pipeline phases and execution status are conflated across ~6 storage locations, and the DB and the filesystem both claim to be the source of truth. The system spends 57% of its diagnostic budget (12 of 21 doctor checks) defending surfaces this design creates — and that immune system has itself rotted.

### Evidence
All verified 2026-07-10 against the live DB (`~/.claude/pd/entities/entities.db`, schema v17, 533 entities / 7 workspaces) and source:

- **Split identity:** `uuid` is PK and half the schema joins on it (relations, tags, dependencies, OKR, `parent_uuid`); `workflow_phases` (PK `type_id`) and `phase_events` join on the business key instead.
- **Racy, colliding business key:** number allocation is dual — the atomic `next_sequence_value` (`database.py:9360`, `BEGIN IMMEDIATE`) is used in production only by task promotion (live `sequences` table has zero `feature` rows), while features get numbers from an unlocked filesystem scan (`create-feature.md:48` "Find highest number … and add 1"). Two concurrent sessions collide deterministically. `UNIQUE(workspace_uuid, type_id)` scopes uniqueness per workspace: **7 cross-workspace type_id collisions live in the DB today**, incl. `project:P001` in three workspaces.
- **Phase/status conflation:** `entities.status` is free TEXT with **no CHECK** (10 live values incl. 13 empty strings; `active` and `in_progress` coexist for the same lifecycle class). `workflow_phases.workflow_phase` CHECK is the **union of four state machines' vocabularies** (feature pipeline / brainstorm / backlog / 5D) in one column. `kanban_column` is derived by `derive_kanban(status, phase)` (`kanban.py:25`) — status wins for terminal states, phase otherwise. Plus `last_completed_phase`, `metadata.phase_timing`, and the `.meta.json` projection: ~6 places state lives.
- **Dual truth → noise:** 601 doctor warnings at session start; ~96% (579) is DB ↔ `.meta.json`/filesystem drift. The largest bucket (320 `entity_orphans`) is substantially **false positives**: checks still query `entity_type`/`project_id` — columns dropped by migrations 11/12 — and the `sqlite3.Error` is silently swallowed (`checks.py:1402`), so `feature:114` (in the DB, `completed`) is reported "no entity in DB".
- **Maintenance tax:** 22 copy-rename table rebuilds across the migration chain; a four-feature repair chain (114→117) existed solely to fix migration/identity damage; schema version tracked in 3 inconsistent places (`PRAGMA user_version`=0, `_metadata.schema_version`=17, `EXPORT_SCHEMA_VERSION`=1).

## Current State Assessment

| Aspect | Today | Consequence |
|---|---|---|
| Identity | uuid PK + `type_id` business key, different tables join on each | dual-key drift; type_id rewrites on promotion |
| Numbering | atomic sequence (tasks only) + filesystem scan (features) | races, collisions, gap anxiety |
| State | status (free text) + workflow_phase (4-vocab enum) + kanban_column (derived) + last_completed_phase + phase_timing + .meta.json | translation functions, sync checks, drift |
| Truth | DB and files both authoritative | 579 drift warnings; reconcile subsystem |
| Workspaces | per-workspace UNIQUE + allowlist + 4 doctor checks | split-brain class of bugs (feature 108) |
| Auditability | phase_events exists but is one of several write paths | invariant enforced by grep + doctor, not structure |

## Goals

1. One identity mechanism, one source of truth, one audit trail — fragility surfaces removed rather than defended.
2. Clean separation of authoring pipeline (`pipeline_phase`) from execution status (`execution_status`).
3. Multi-workspace operation as a first-class, boring capability.
4. Shrink the defense apparatus (doctor, reconcile, guards) to match the smaller attack surface.

## Success Criteria

- [ ] One key type: every table joins on `uuid`; zero joins on business keys (verify: schema inspection + grep for `type_id` FK usage = 0).
- [ ] `replay(events) == projection` property test passes field-by-field, including per-phase timing/iterations/reviewerNotes/skippedPhases.
- [ ] Doctor session-start warnings on a healthy workspace: **0** (from 601).
- [ ] Two concurrent `create-feature` runs (same and different workspaces): zero collisions, zero user-visible conflict handling.
- [ ] Kanban board and phase queries read different columns with **zero translation functions** (`derive_kanban` deleted; grep = 0).
- [ ] Any entity's full history reconstructible from one query over `events`.
- [ ] Schema version lives in exactly one location.
- [ ] **Backfill completeness gate:** post-rebuild reconciled entity/workspace counts match the pre-rebuild live census (533 / 7 as of 2026-07-10, re-censused at cutover), OR every delta is itemized in the import anomaly report and explicitly acknowledged before cutover.

## User Stories

### Story 1: Multi-workspace operator
**As a** developer using pd across 7 projects **I want** lists, boards, and lineage scoped to my current workspace by default with an explicit `--all-workspaces` view **So that** entities from other projects never pollute my view and cross-workspace duplicates cannot exist as an error class.
**Acceptance:** board/list/lineage default to current workspace; all-workspaces view labels each row; no allowlist maintenance anywhere.

### Story 2: Workflow engine as sole state writer
**As the** workflow engine **I want** every state change to be an appended event with current state derived from events **So that** no code path (including raw SQL) can mutate state without leaving an audit record.
**Acceptance:** state is not independently writable (view over events, or projection writable only inside the event-append transaction); feature-109's deferred runtime-enforcement hole (`109/spec.md:378`) is closed structurally, not by grep.

### Story 3: Auditor
**As a** user debugging workflow behavior **I want** `history <entity>` to show the complete ordered event stream (who/when/what axis/from→to) **So that** any state question is answered by one query, not by diffing six storage locations.
**Acceptance:** one query returns full history; replay of that history reproduces current state exactly.

### Story 4: Renaming a scope-pivoted feature
**As a** user whose feature pivoted mid-flight **I want** to rename/renumber it as a plain metadata update **So that** identity, relations, and history are untouched (subsumes backlog #00063).
**Acceptance:** rename touches only display fields; all FKs/events unaffected; an event records the rename.

### Story 5: Concurrent creation
**As** two parallel sessions creating features **I want** allocation to be atomic in the DB **So that** both get distinct display numbers without coordination.
**Acceptance:** the filesystem-scan allocator in `create-feature.md:48` no longer exists; allocation goes through the atomic sequence for all kinds.

## Requirements

### Functional
- **FR-1 (R2.1 — single truth):** The DB is the sole source of truth for entity state; ALL workflow management flows through MCP tools, never file edits. Unconditional: no authoritative local state file exists. Conditional on OQ-1 resolving "keep `.meta.json`": the file is a read-only projection written exclusively by the DB layer, and the `data-file-guard` hook (per the meta-json-guard-deadlock RCA) recognizes that writer and blocks all others. If OQ-1 resolves "drop it", the guard-rewire clause is void.
- **FR-2 (R2.2 — events):** `events(id, entity_uuid FK, event_type, axis [pipeline|execution|lifecycle], from_value, to_value, actor, timestamp, payload JSON)` is append-only and is the ONLY write path for state. Generalizes today's `phase_events`. Full audit trail reconstructible from this table alone.
- **FR-3 (structural enforcement):** Current state is a projection of events, implemented as a VIEW over latest-event-per-axis. Raw SQL must not be able to bypass the event path. Any alternative implementation must satisfy that invariant *structurally* (not via code discipline, triggers-as-guards, or grep checks — those are the rejected approaches).
- **FR-4 (R2.4 — identity):** UUIDv7 is the sole identity, used by every table incl. the workflow-state and events tables. No uniqueness constraint on any human-readable field.
- **FR-5 (display identity):** `display_id` (e.g. `F-1042`) per workspace, allocated via the existing atomic `next_sequence_value` extended to all kinds. Purely presentational; rename/renumber = `update_entity` on display metadata + a recorded event. Registration validates non-empty name/slug (blank display fields helped corrupt the old DB — P003 prd.md:20-21).
- **FR-6 (R2.5 — two axes):** `pipeline_phase` (brainstorm→specify→design→create-plan→implement→finish; NULL for non-authored kinds) and `execution_status` (small universal Kanban enum) are separate fields with separate CHECKs. Kanban board columns render `execution_status`; card badge renders `pipeline_phase`. `derive_kanban` is deleted.
- **FR-7 (one engine):** A single per-kind transition-machine router replaces the split `ENTITY_MACHINES` + `WorkflowStateEngine` pair (the collapse `lifecycle_class` was added to enable, deferred through 109→111). Project-kind transitions and projections are ported instead of remaining the unowned special case (`110/spec.md:36,48`).
- **FR-8 (dependency cascade):** `entity_relations.kind` expands to include `blocks` (real rows replace the `blocked_by` metadata JSON array). When a completion event lands, downstream entities whose blockers are all resolved flip `execution_status blocked → ready` via a follow-on event (re-homes F052's `_cascade_unblock`).
- **FR-9 (R2.3 — multi-workspace):** `workspaces` table retained; resolution precedence unchanged (env > flag > workspace.json > recovery); split-brain fails loud (feature-108 behavior preserved). Cross-workspace links are ordinary uuid references — the allowlist table and its doctor checks are removed. Queries take a workspace scope; UI gets a workspace switcher.
- **FR-10 (degraded mode = read-only):** If the DB is unavailable, all state mutations fail loud; reads serve the last projection. No fallback state-file writer exists — `_write_meta_json_fallback` and equivalents do not survive (a degradation path that writes reopens the dual-truth hole).
- **FR-11 (projection fidelity):** The projection losslessly reproduces everything `.meta.json` carries today: per-phase `{started, completed, iterations, reviewerNotes}`, `skippedPhases[]`, `branch`, `mode`, `brainstorm_source`/`backlog_source` — all derivable from event payloads.
- **FR-12 (rebuild + cleanup):** New DB file, schema counter reset, ONE version location. Backfill by replay (see Migration Path). Delete the Migration-11 transition shims (`database.py:5902` compatibility shim; legacy `project_id` kwarg at `entity_server.py:551`). Doctor: remove the 12 identity/workspace/sync checks whose surfaces disappear; fix-or-delete the rotted checks querying dropped columns.

### Non-Functional
- **NFR-1 (concurrency):** Event-append + projection-update is ONE `BEGIN IMMEDIATE` transaction using the shared `sqlite_retry` decorator and standardized `busy_timeout` (F062 primitives applied to the new tables). Display-id allocation stays atomic. No new concurrency machinery.
- **NFR-2 (runtime):** `requires-python >= 3.14` for stdlib `uuid.uuid7` (venv verified at 3.14.6; `pyproject.toml` currently `>=3.12` — this was the blocker that deferred UUIDv7 in feature 108 F6 / backlog #00359).
- **NFR-3 (latency):** Cluster 1 captures the current session-start read latency (p50/p95) as a recorded baseline; if `.meta.json` is dropped, DB-direct reads must not exceed that baseline. (The baseline measurement converts OQ-1 into a pass/fail decision.)
- **NFR-4 (auditability of the audit):** Event rows are immutable (no UPDATE/DELETE path); `actor` recorded per OQ-2.

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| DB unavailable mid-phase | Mutations fail loud with recovery hint; reads from last projection; no file fallback write | FR-10; degradation-that-writes = no enforcement |
| Concurrent create, same workspace | Both succeed with distinct display_ids (atomic sequence) | FR-5/NFR-1 |
| Concurrent create, different workspaces | Both succeed; display collision across workspaces is cosmetic and allowed | identity is uuid, not display |
| workspace.json ↔ DB split-brain | Fail loud with doctor hint + session-restart note (MCP caches workspace uuid at startup) | feature-108 behavior preserved |
| Malformed legacy rows at backfill (empty ids, duplicate P001s) | Import dedupes/normalizes; anomalies listed in the import report, not silently skipped | replay checksum report |
| Replay divergence (projection ≠ replay) | Property test fails CI; `reconcile` = replay repairs the projection | FR-3/FR-11 |
| Event append fails mid-transaction | Whole transaction rolls back; no partial state | NFR-1 |

## Constraints

### Behavioral (Must NOT do)
- No state write path outside `events` — including on DB failure. Rationale: single-writer is the load-bearing invariant.
- No LLM/manual edits to projection files. Rationale: same.
- No business-key uniqueness constraints. Rationale: reintroduces the collision/renumber class.

### Technical
- SQLite + WAL remains the store (no server DB, no cloud sync) — Evidence: current posture adequate at 533 entities / 7 workspaces.
- MCP servers cache workspace uuid at startup — identity operations require session restart notes (Evidence: split-brain fix, `database.py:5861-5890`).

## Approaches Considered

| Approach | Verdict | Why |
|---|---|---|
| Files-canonical, DB as rebuildable index | Rejected (user decision R2.1) | DB-canonical chosen; files become projections |
| Migrate schema v17 → v18 in place | Rejected | The 114→117 chain demonstrates the repair tax of in-place migration; private tooling allows clean rebuild |
| Writable `state` table + trigger guards | Rejected in favor of view-over-events | Structural enforcement beats guard maintenance (closes 109's deferred hole) |
| Keep `derive_kanban` with better inputs | Rejected | Derivation IS the conflation; two axes need two columns |

## Cluster Sequencing (PROPOSED decomposition hint for create-project — a judgment call, not settled scope)

1. v2 schema + events core + view projections (FR-2/3/4, NFR-1/2)
2. Transition-engine unification, per-kind router incl. project-kind port (FR-7)
3. Display identity + atomic allocation + kill filesystem allocator (FR-5)
4. `.meta.json` projection decision + data-file-guard rewire + degraded mode (FR-1/10/11, OQ-1)
5. Backfill/rebuild tool + old-DB read-only window (FR-12, Migration Path)
6. Doctor shrink + rotted-check deletion (FR-12) — **the rotted-check fix is extractable pre-work, independent of the redesign**
7. Kanban UI rewire to `execution_status` + workspace switcher (FR-6/9)

## Migration Path

Rebuild, don't migrate. New DB file; backfill by replaying: existing entities → `entity_created` events with fresh UUIDv7s; existing `phase_events` map onto the new axes; status/kanban derived once at import via the current `derive_kanban` logic, then that logic is deleted. Import produces a checksum/anomaly report (counts per kind/workspace, dedupes performed, malformed rows normalized). Old DB kept read-only for 30 days as escape hatch. OQ-4 governs history fidelity.

## Strategic Analysis

### Pre-Mortem Advisor
- **Core Finding:** The likeliest failure is silent — replay/projection divergence or a stale cached workspace uuid — not a loud crash.
- **Analysis:** Event-sourced rebuilds fail quietly when projections drift from replay or when backfill normalizes lossily. The MCP servers cache workspace identity at startup (the split-brain fix required session restarts), so identity-affecting operations have a hidden ordering dependency. Dropping `.meta.json` without measuring hook latency risks a regression that shows up as "sessions feel slow", not as an error.
- **Key Risks:** silent replay bugs; import lossiness; hook latency; the express-mode phase-subset seam (workflow track) arriving after the schema freezes.
- **Recommendation:** property test (`replay == projection`, field-by-field) in CI from cluster 1; import checksum report; measure latency before OQ-1 decision; resolve OQ-6 jointly with the workflow track's design phase before schema freeze.
- **Evidence Quality:** strong (live-DB queries, shipped-feature history, verified this session).

### Opportunity-Cost Advisor
- **Core Finding:** The do-nothing path has a demonstrated recurring tax; rebuild concentrates that cost once.
- **Analysis:** The current model has already consumed a four-feature repair chain (114→117), 22 copy-rename rebuilds, a cross-workspace allowlist + triage tooling, and 12 standing doctor checks — and still produces 601 warnings, a third of them spurious. Each future feature touching identity or state pays the same class of tax. The rebuild's one-time cost buys deletion of the reconcile-drift category (~96% of warnings), most of the doctor, and the migration treadmill.
- **Key Risks:** rebuild scope creep into the workflow track (mitigated: phase vocabulary frozen, seam single-sourced at OQ-6).
- **Recommendation:** proceed; extract the rotted-doctor-check fix immediately as independent pre-work so the diagnostic signal is trustworthy during the rebuild.
- **Evidence Quality:** strong.

## Supersedes (prior decisions this PRD deliberately reverses or retires)

- **"Event sourcing is overkill; a simple audit table suffices"** — non-goal in four prior PRDs (enforced-state-machine:207, reactive-entity-consistency:300, state-consistency-consolidation:117, pd-data-model-hardening:57). Reversed by R2.2; those non-goals are no longer binding.
- **`derive_kanban` + authoritative `entities.status`** (F052/F036) — replaced by the two-axis model.
- **`project_id`-scoped identity + `UNIQUE(project_id, type_id)` + per-project sequences** (F065) — replaced by workspace_uuid + uuid identity + non-unique display_id.
- **The 114→117 migration-repair chain** (M12 stub-trap recovery, M13–M17 down-migrations, cross-workspace allowlist + triage tooling, `_UNKNOWN_WORKSPACE_UUID` re-attribution, audit-emit counters, AST whitelist sweeps, strict entity_id fixture format) — moot under rebuild; the invariant it defended becomes structural.

## Non-Goals

- No changes to the phase vocabulary (workflow track owns it; canonical 6 phases stay) — Rationale: keeps this track unblocked and the seam single-sourced.
- Tasks stay artifacts, NOT first-class entities — Rationale: fractal-work-management (`20260320-050414`, never promoted) deliberately out of scope; recorded so it isn't silently lost.
- No multi-writer support beyond WAL + busy_timeout; no cloud sync — Rationale: current posture adequate.
- Memory-db cleanup items (112/114 chain) — Rationale: different database.

## Out of Scope (This Release)

- `relates_to`/`duplicates` relation kinds — Future: add when an API needs them (deferred by 111, stays deferred).
- Namespace-prefixed display ids (`pd/backlog-001`) — Future: only if cross-workspace display collisions prove confusing in practice.

## Risks

| Risk | Mitigation |
|---|---|
| Silent replay/projection divergence | CI property test from cluster 1; import checksum report |
| Stale cached workspace uuid in MCP servers | Restart requirement documented in tool errors (existing split-brain pattern) |
| Hook latency regression if `.meta.json` dropped | Measure first; OQ-1 gates the decision |
| Express-mode seam forces late schema change | OQ-6 resolved jointly before schema freeze |
| Backfill loses history nuance | OQ-4 decides fidelity explicitly; anomaly report makes loss visible |

## Open Questions

1. Does `.meta.json` survive as a projection for hook-speed reads, or do hooks query SQLite directly? (Measure session-start latency; gates FR-1 shape.)
2. Event `actor` granularity: session id, agent name, or both?
3. `execution_status` final enum: is `ready` distinct from `backlog`? Do `agent_review`/`human_review` (0 rows ever) return or stay dead?
4. Backfill fidelity: full historical event import vs snapshot-import (`imported` event per entity)?
5. Workspace identity: keep random `workspace.json` uuid, or derive from git remote hash? If derived, a `workspace merge` tool becomes required (reactive-entity-consistency R2.5); with random uuid it stays low priority.
6. Pipeline-phase validity: per-kind only, or per-(kind, mode)? Express mode (workflow track R1.3) records skipped phases — the schema must represent phase subsets without a second vocabulary. **Cross-track seam; this PRD owns the representation decision, the workflow PRD references it.**
7. PR-review surface for state changes: does the F110 `pd-state.diff.md` generator survive, or do queryable events (`show-status --diff`) replace it?

## Next Steps

1. Extract pre-work: fix/delete the rotted doctor checks (independent, immediate).
2. `/pd:create-project` on this PRD → decomposition (Cluster Sequencing above is the proposed starting point).
3. Resolve OQ-1/OQ-6 during the design phase; OQ-6 jointly with the workflow track.

## Reference Files

- Live DB census + schema: `plugins/pd/hooks/lib/entity_registry/database.py` (DDL, migrations 9-17, `next_sequence_value:9360`, shim `:5902`), `~/.claude/pd/entities/entities.db`
- Conflation sites: `plugins/pd/hooks/lib/workflow_engine/kanban.py:25`, `engine.py:214-272`, `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:18`, `plugins/pd/hooks/lib/transition_gate/models.py:13`
- Rotted checks: `plugins/pd/hooks/lib/doctor/checks.py:709,988,1083,1391-1403`
- Prior work folded in: `docs/projects/P003-entity-system-redesign/`, features 108-111 specs/retros, `docs/brainstorms/20260320-050414-reactive-entity-consistency.prd.md`, `20260308-204500-enforced-state-machine.prd.md`, `20260324-153947-sqlite-concurrency-defense.prd.md`, `docs/rca/20260318-meta-json-guard-deadlock.md`
- Companion track: `docs/brainstorms/20260710-153500-workflow-rebuild.prd.md`

## Review History

### Review 1 (2026-07-10) — pd:prd-reviewer
- **Verdict:** APPROVED, zero blockers. ~12 sampled file:line citations all verified exact; R2.1-R2.5 map cleanly to FRs.
- **Warnings addressed in this revision:** FR-3's projection-table "alternative" removed (it violated FR-3's own raw-SQL invariant, Story 2, and the Approaches decision — VIEW is now the single stated approach); backfill completeness/cutover gate added to Success Criteria; NFR-3 made testable via a recorded latency baseline; FR-1's guard-rewire clause marked conditional on OQ-1; FR-5 citation repointed to P003 prd.md:20-21.
