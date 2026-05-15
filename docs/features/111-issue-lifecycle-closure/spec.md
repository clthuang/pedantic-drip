# Feature 111 — Issue Lifecycle Closure

- **Project:** P003-entity-system-redesign — Milestone M4 (Phase 4 — Lifecycle Closure) — final feature in P003
- **Depends on:** 109-polymorphic-taxonomy-and-event (post-migration-12 baseline; `entity_type` column DROPPED, `type`/`kind`/`lifecycle_class` triple ACTIVE); 110-markdown-projections-and-gener (post-migration-13 `entity_display` + projection sealed write path)
- **Brainstorm source:** `docs/projects/P003-entity-system-redesign/prd.md`
- **Status:** revision 3.4 (rev 3.3 was phase-reviewer-approved; rev 3.4 patches in design-reviewer iter 1 findings: status-only model for bug/task (drops ENTITY_MACHINES entries; resolves Blocker B1 — workflow_phases CHECK incompatibility); EntityNotFoundError + InvalidCloseTargetError exception classes pinned (FR-EX, Blocker B2); down-migration pre-flight check (FR-MR.9, AC-MR.10/11); AC-10.11 state-machine-bypass behavior; Pins L (entities.status no CHECK) and M (workflow_phases.workflow_phase CHECK gaps))

## §1 Background and SUT-Verified Baseline

This feature is the closing chapter of project P003 Phase 4. It bundles three sub-features:

- **F9 — `issue_spawn(parent_uuid, kind, summary)` MCP** — spontaneous mid-flight issue capture; appends a `spawned_child` phase_event on the parent (no parent phase change); creates a new `type='work', kind=<bug|task>` entity and returns its uuid.
- **F10 — `complete_phase(closes=[uuid...])` atomic closure linkage** — extends the existing MCP to optionally close N referenced entities in the same transaction: writes `entity_relations(from_uuid, to_uuid, kind='fixes')` rows AND transitions each closed entity to its **kind-appropriate terminal state** per `ENTITY_MACHINES`.
- **Cleanup** — remove free-text-suffix parsers (`(closed: ...)`, `(promoted → ...)`, `(fixed: ...)`) at `backfill.py` and `doctor/checks.py`. These were superseded by structured DB state in features 109–110.

### §1.1 Pre-spec codebase-explorer survey (empirical SUT pins, revision 2)

| Concern | Empirical SUT pin (verified) | Spec implication |
|---|---|---|
| Schema baseline | `MIGRATIONS` tops at key 13 (`database.py:4326`). `_migration_13_entity_display` created the `entity_display` table. No migration 14 stub. | Feature 111 introduces Migration 14: widen (type, kind) CHECK to admit `kind='bug'`; widen phase_events.event_type CHECK to admit `'spawned_child'`; create `entity_relations` table. |
| Entities schema post-12 | `entity_type` column DROPPED at Group 7, Task 7.3 of feature 109 (`database.py:3195+`). Current discriminator triple: `type TEXT NOT NULL DEFAULT 'work'`, `kind TEXT NOT NULL DEFAULT 'feature'`, `lifecycle_class TEXT NOT NULL DEFAULT 'feature_flow'`. | All issue_spawn writes go through (type, kind, lifecycle_class). NO references to dropped `entity_type` column. |
| Current (type, kind) CHECK | `database.py:2986-2999` and `:3298-3304` admit: `(type='workspace' AND kind='workspace')`, `(type='brainstorm' AND kind='brainstorm')`, `(type='container' AND kind='project')`, `(type='work' AND kind IN ('feature','backlog','initiative','objective','key_result','task'))`. Comment at `:2993` explicitly notes: "feature 111 narrows this when bug/task get first-class CHECK pairs." | Migration 14 widens the work-kind set: `kind IN ('feature','backlog','bug','initiative','objective','key_result','task')`. ('task' already present.) |
| `entity_relations` table | DOES NOT EXIST anywhere in codebase. | Migration 14 creates it: see FR-MR.1 DDL block. |
| `complete_phase` MCP signature | `workflow_state_server.py:1809` — no `closes=` parameter. `_process_complete_phase` at `:1086` also no `closes`. | F10 extends both signatures with `closes: list[str] = None` (list of entity uuids). |
| `ENTITY_MACHINES` dict | `entity_lifecycle.py:18-56` — only `brainstorm` and `backlog` machines. NO `bug` machine. Comment at `:14` says "Single registry keyed by entity_type" (legacy name — actually keyed by `kind` post-109). | Feature 111 adds `ENTITY_MACHINES['bug']`: states `open` (initial), `resolved`, `closed`, `wont_fix` (all terminal); transitions `open → {resolved, closed, wont_fix}`. |
| `register_entity` signature | `database.py:5156` accepts `entity_type` parameter as the kind-name. Internal mapping at `:5188+` translates `entity_type → (type, kind, lifecycle_class)` per the migration-12 backfill mapping (e.g., `entity_type='backlog' → type='work', kind='backlog', lifecycle_class='work_flow'`). | issue_spawn passes `entity_type='bug'`. register_entity's internal mapping is extended to: `bug → (type='work', kind='bug', lifecycle_class='bug_flow')`. |
| `register_entity` strict-format | Post-feature-110: entity_id must match `^\d+-.+` (EntityIdFormatError otherwise, raised at `database.py:5271`). `_strict_id_format=False` bypasses. | issue_spawn uses the auto_id path via `id_generator.generate_entity_id(_db, 'bug', name, project_id)` to produce a conformant `{seq}-{slug}` id. |
| `phase_events.event_type` CHECK | `database.py:3402` — post-12 CHECK admits 7 values: `('started','completed','skipped','backward','entity_created','entity_status_changed','entity_promoted')`. NO `'spawned_child'` value. | Migration 14 widens the CHECK to include `'spawned_child'` so issue_spawn can emit the PRD-Story-5-mandated event_type on the parent. |
| `kanban_column` CHECK | `database.py:743` admits 8 columns: `('backlog','prioritised','wip','agent_review','human_review','blocked','documenting','completed')`. | issue_spawn MUST NOT modify the parent's `kanban_column`. AC-9.2 asserts byte-equality pre/post. |
| MCP tool registration patterns | `@mcp.tool()` decorator on async functions in `entity_server.py` / `workflow_state_server.py`. | F9 lands in `entity_server.py` (entity creation surface) per existing pattern. F10 extends existing tool in `workflow_state_server.py`. |
| Free-text suffix parsers | `backfill.py:428` parses `(closed:`, `(fixed:`, `(already implemented` markers. `doctor/checks.py:991,995` parses `(promoted →`, `(closed:` markers. | Cleanup removes the parsers AND their call-site logic. Tests pivot to DB-state inputs. Historical prose markers remain untouched in retro/spec markdown files — no backfill of markers into entity_relations. |
| `VALID_ENTITY_TYPES` Python constant | `database.py:4534` — 8 values (backlog, brainstorm, project, feature, initiative, objective, key_result, task). Used as forward-compat reference for register_entity callers. | Feature 111 extends to 9 values: adds `'bug'`. |

### §1.2 Empirical baseline assertions (load-bearing pins, must be true at design-phase entry)

These are the concrete pre-conditions feature 111 depends on. If any pin drifts before implementation, design-phase blocks and re-pins.

- **Pin A — `schema_version=13`:** `sqlite3 entities.db "SELECT MAX(version) FROM schema_migrations"` → `(13,)`.
- **Pin B — `entity_display` table present:** `sqlite3 entities.db ".tables"` includes `entity_display`.
- **Pin C — `entity_type` column ABSENT on entities table:** `sqlite3 entities.db "PRAGMA table_info(entities)"` does NOT include a row where `name='entity_type'`.
- **Pin D — Current (type, kind) CHECK constraint string includes `'feature','backlog','initiative','objective','key_result','task'` (no 'bug'):** `sqlite3 entities.db "SELECT sql FROM sqlite_master WHERE name='entities'"` → substring match.
- **Pin E — Current phase_events.event_type CHECK does NOT include `'spawned_child'`:** `sqlite3 entities.db "SELECT sql FROM sqlite_master WHERE name='phase_events'"` → no `'spawned_child'` substring.
- **Pin F — `entity_relations` table absent:** `.tables` does NOT include `entity_relations`.
- **Pin G — Free-text parsers present at known sites:** `grep -nE "(closed:|fixed:|promoted →)" plugins/pd/hooks/lib/backfill.py plugins/pd/hooks/lib/doctor/checks.py` returns exactly 4 hits at `backfill.py:428` (`(closed:`, `(fixed:`, `(already implemented`) and `doctor/checks.py:991, 995` (`(promoted →`, `(closed:`). If a 5th parser site appears during design phase, re-spec instead of silently expanding scope. Post-feature-111, this returns 0 hits across production code.
- **Pin H — `phase_events.phase` column is NULLABLE:** `sqlite3 entities.db "PRAGMA table_info(phase_events)"` returns `notnull=0` for the `phase` column. (If pin fails, Migration 14 adds a column-relax step. Currently assumed true per migration-12 widening at `database.py:3395+`.)
- **Pin I — Live-DB task entity count is 0:** Empirically verified pre-design: `sqlite3 ~/.claude/pd/entities/entities.db "SELECT COUNT(*) FROM entities WHERE entity_type='task'"` returns `0` on the current live DB. (The DB queried is on a PRE-feature-109 schema — uses `entity_type` column; post-109 query would be `WHERE kind='task'`. Migrations 12-13 auto-run at next session start.) Implication: FR-MR.5 task remap UPDATE is an operational no-op in production; only test fixtures exercise the remap path.
- **Pin J — Pre-feature-109/110 schema state in live DB:** The live entities.db is currently on a pre-feature-109 schema (no `schema_migrations` table; entities table has `entity_type` column). Features 109 and 110 migrations 11-13 are in the codebase but have not yet run against the live DB. This is a deliberate state — they run automatically on next pd session start via `EntityDatabase._migrate()`. Feature 111's Migration 14 chains on top of 13 — design phase confirms the migration runner enforces strict v0→v13→v14 ordering.
- **Pin K — `lifecycle_class` column has NO CHECK constraint:** Empirically verified at `database.py:2983` (post-migration-12 entities table) and `:3294` (post-Group-7 entities table) — `lifecycle_class` is declared `TEXT NOT NULL DEFAULT 'feature_flow'` with no CHECK clause. Implication: adding new lifecycle_class values (`bug_flow`, `task_flow`) does NOT require widening any CHECK constraint. Migration 14 omits lifecycle_class CHECK widening entirely.
- **Pin L — `entities.status` column has NO CHECK constraint:** Verified at `database.py:5334+` (entities table CREATE in migration-12) — `status TEXT` (nullable, no CHECK). Implication: `update_entity(uuid, status=<any-string>)` is a free write at the DB layer. Validation lives in application code (status-only model per FR-BL.2). Future tightening (e.g., per-kind status CHECK via a trigger) is out of scope.
- **Pin M — `workflow_phases.workflow_phase` CHECK does NOT admit bug/task states:** At `database.py:743-748`, the CHECK admits `('brainstorm','specify','design','create-plan','create-tasks','implement','finish','draft','reviewing','promoted','abandoned','open','triaged','dropped','discover','define','deliver','debrief')` — `'resolved'`, `'closed'`, `'wont_fix'` are ABSENT. Migration 14 does NOT widen this — bug/task entities use the status-only model (FR-BL) and skip workflow_phases entirely.

## §2 Goals

1. **Mid-flight issue capture without phase disruption.** `issue_spawn(parent_uuid, kind, summary)` creates a new `type='work', kind=<bug|task>` entity and appends a `spawned_child` event on the parent — parent's `workflow_phase` AND `kanban_column` are NOT modified. The interruption is non-destructive (PRD Story 5).
2. **Atomic closure linkage with kind-aware terminal state.** Closing N entities alongside a feature's `complete_phase('finish')` is a single transaction — either all closes succeed or none persist. `entity_relations` rows + per-kind terminal-state transitions atomic (PRD Story 6).
3. **Structured replacement for free-text status markers.** All `(closed: ...)`, `(promoted → ...)`, `(fixed: ...)` parsers removed from production code. The DB columns (`entities.status`, `entities.parent_uuid`, `entity_relations`) become the sole sources of truth at read time. Historical free-text markers in retro/spec/backlog prose remain untouched; only the parser logic is gone.

## §3 Functional Requirements

### FR-9 — `issue_spawn` MCP

- **FR-9.1 — Signature.** New async MCP tool in `plugins/pd/mcp/entity_server.py`:
  ```python
  @mcp.tool()
  async def issue_spawn(
      parent_uuid: str,
      kind: str,          # one of: "bug" | "task"  (per PRD Story 8 work.kind ontology)
      summary: str,       # human-readable description, becomes entity.name
      *,
      workspace_uuid: str | None = None,
      project_id: str | None = None,   # legacy alias; resolved via existing register_entity logic
      metadata: dict | None = None,    # arbitrary caller-supplied JSON; merged into entities.metadata
  ) -> str  # returns the new entity's uuid
  ```
- **FR-9.2 — Entity creation contract.** `issue_spawn` calls `register_entity(entity_type=kind, entity_id=<auto>, name=summary, parent_uuid=parent_uuid, status='open', workspace_uuid=..., metadata=metadata)`. The `entity_id` is generated via `id_generator.generate_entity_id(_db, kind, name, project_id)` (auto_id path) — produces conformant `{seq}-{slug}` so EntityIdFormatError cannot fire. The internal `entity_type → (type, kind, lifecycle_class)` mapping in register_entity is extended: `kind='bug' → (type='work', kind='bug', lifecycle_class='bug_flow')`; `kind='task' → (type='work', kind='task', lifecycle_class='task_flow')` (NEW lifecycle_class value; declarative tag only — see FR-BL.3 + FR-MR.5). NO `init_entity_workflow` call follows registration (status-only model per FR-BL).
- **FR-9.3 — Parent phase_event append.** After entity creation, `issue_spawn` MUST `append_phase_event(type_id=<parent_type_id>, event_type='spawned_child', phase=NULL, metadata={"child_uuid": <new_uuid>, "child_kind": kind, "child_name": summary})`. The parent's `workflow_phases.workflow_phase` AND `workflow_phases.kanban_column` columns are NOT modified (column-level invariance — `updated_at` may tick due to triggers; AC-9.2 asserts column-level, not row-level, equality).
- **FR-9.4 — Returns.** Returns the new entity uuid (string).
- **FR-9.5 — kind enum.** `kind` value MUST be one of `{"bug", "task"}` (per PRD Story 8 `work.kind` ontology). Invalid kind raises `ValueError` BEFORE any DB write.
- **FR-9.6 — Parent existence + kind check.** `parent_uuid` MUST resolve to an existing entity row in the same workspace (within the resolved `workspace_uuid`). The resolved parent's `kind` MUST be in `{'feature', 'backlog', 'project'}` — issue_spawn from `brainstorm`, `workspace`, or `bug`/`task` parents raises `ValueError("invalid_parent_kind: {kind}; expected feature|backlog|project")`. If parent does not exist, raise `ValueError("parent_not_found: {parent_uuid}")`. Both raised BEFORE any DB write. No partial state created.
- **FR-9.7 — entity_display 1:1 invariant.** Per feature 110's invariant, every `register_entity` write atomically produces an `entity_display(entity_uuid, display_seq, display_slug)` row. issue_spawn inherits this — no additional plumbing needed. AC-9.7 verifies the row exists post-call.
- **FR-9.8 — Doctor check_status_write_path compliance.** issue_spawn implementation MUST go through `append_phase_event()` for the parent event (no direct INSERT into phase_events). The AST-based doctor check (`check_status_write_path`) MUST pass on the new code.
- **FR-9.9 — Metadata merge semantics.** Caller-supplied `metadata` dict is shallow-merged into `entities.metadata` JSON with **system-supplied keys taking precedence** — callers cannot overwrite reserved keys (the reserved set is owned by register_entity / id_generator and includes any keys it writes internally; issue_spawn does not currently inject reserved keys beyond what register_entity injects). Pinned via AC-9.9 with the synthetic `{"severity": "high", "parent_uuid": "evil"}` → resulting metadata has `severity='high'` AND no `parent_uuid` key (parent linkage lives in entities.parent_uuid column, not metadata).

### FR-bug-task-lifecycle — status-only tracking (no ENTITY_MACHINES entry)

**Design-phase patch (per design-reviewer iter 1 blocker B1):** bug and task entities use a **status-only tracking model** — they do NOT have `workflow_phases` rows, do NOT go through `transition_entity_phase`, and do NOT need entries in `ENTITY_MACHINES`. Their lifecycle is encoded entirely by:
1. `_KIND_TO_TYPE_LIFECYCLE` mapping (`kind='bug' → lifecycle_class='bug_flow'`; `kind='task' → lifecycle_class='task_flow'`) — declarative tag.
2. Initial `status='open'` set at `register_entity` time by `issue_spawn`.
3. `_CLOSES_TERMINAL` dict (`'bug_flow' → 'closed'`; `'task_flow' → 'closed'`) consulted by `complete_phase(closes=)`.
4. Direct `update_entity(uuid, status=<terminal>)` for transitions outside closes= (e.g., a caller marks a bug as 'resolved' or 'wont_fix' directly).

**Why this departs from rev 3.3:** The `workflow_phases.workflow_phase` CHECK constraint (`database.py:743-748`) does NOT admit `'resolved'`, `'closed'`, `'wont_fix'`. Widening it would require yet another copy-rename of `workflow_phases`. The status-only model is simpler, avoids the CHECK widening, and matches the "issues are lightweight" mental model from PRD Story 5 ("first-class MCP for spontaneous mid-flight issue capture").

- **FR-BL.1 — No ENTITY_MACHINES entry.** `ENTITY_MACHINES['bug']` and `ENTITY_MACHINES['task']` are NOT added. Neither kind goes through `init_entity_workflow` or `transition_entity_phase`. No `workflow_phases` row is created at issue_spawn time.
- **FR-BL.2 — `entities.status` is the sole state field.** Valid values for `kind='bug'`: `{'open', 'resolved', 'closed', 'wont_fix'}`. Valid for `kind='task'`: `{'open', 'closed'}`. There is no DB-level CHECK on `status` (per Pin L below); validation is application-layer (in `issue_spawn` initial-status + `_CLOSES_TERMINAL` terminal derivation). Callers wanting non-`closed` terminals for bugs call `db.update_entity(uuid, status=<terminal>)` directly.
- **FR-BL.3 — lifecycle_class declarative.** `lifecycle_class='bug_flow'` / `'task_flow'` exist as discriminator tags on the entities row — consumed by `_CLOSES_TERMINAL` to derive the closes= terminal. No state-machine code consults them otherwise.
- **FR-BL.4 — Existing test fixtures with `kind='task'`, `lifecycle_class='work_flow'` migrated.** Migration 14 includes `UPDATE entities SET lifecycle_class='task_flow' WHERE kind='task'` (operational no-op per Pin I; test fixtures exercise the remap).

### FR-10 — `complete_phase(closes=[uuid...])` atomic closure

- **FR-10.1 — Signature extension.** Both `workflow_state_server.py:1809` (MCP tool) and `_process_complete_phase` at `:1086` (internal dispatcher) gain a new optional kwarg:
  ```python
  closes: list[str] | None = None  # list of entity uuids to atomically close
  ```
  - `closes=None` (default) → existing behavior (no closure linkage).
  - `closes=[]` → no-op for closure (empty list, no rows written), but the rest of complete_phase runs normally.
- **FR-10.2 — Calling-entity uuid resolution.** `_process_complete_phase` resolves the calling entity's uuid via `SELECT uuid, workspace_uuid FROM entities WHERE workspace_uuid=? AND type_id=?` at the **start of the transaction** (before any writes). If lookup fails, raise `EntityNotFoundError("complete_phase: caller not registered: {type_id}")`. The resolved `from_uuid` AND `caller_workspace_uuid` are stashed for use in all subsequent steps. All closed entities (FR-10.3 step 2) MUST also reside in `caller_workspace_uuid` — cross-workspace closure is forbidden (per PRD Goal 1 "Stop cross-workspace contamination structurally").
- **FR-10.3 — Atomic transaction order.** When `closes` is non-empty, the entire `complete_phase` operation runs in a single `BEGIN IMMEDIATE` transaction. Order:
  1. Resolve calling entity's `from_uuid` and `caller_workspace_uuid` (FR-10.2).
  2. For each `uuid` in `closes`: `SELECT type, kind, lifecycle_class, status, workspace_uuid FROM entities WHERE uuid = ?`. If row missing → raise `EntityNotFoundError("complete_phase: closure target not found: {uuid}")`. If `workspace_uuid != caller_workspace_uuid` → raise `InvalidCloseTargetError("complete_phase: cross-workspace closure forbidden: {uuid} is in workspace {other_ws}, caller is in {caller_ws}")`.
  3. For each closed entity, **derive terminal state from its `lifecycle_class`** via the module-level `_CLOSES_TERMINAL` dict (single source of truth — future relation kinds extend this dict without touching dispatch logic):
     ```python
     _CLOSES_TERMINAL = {
         "bug_flow": "closed",   # callers wanting 'resolved'/'wont_fix' use update_entity directly; closes= is for "this feature fixed this bug" only
         "task_flow": "closed",  # new task machine per FR-BM.3
         "work_flow": "dropped", # backlog's existing terminal — feature has subsumed/closed the backlog item
     }
     ```
     - `lifecycle_class='feature_flow'` → NOT in `_CLOSES_TERMINAL`. Raise `InvalidCloseTargetError("complete_phase: feature entities cannot be closed via closes=; use complete_phase('finish') directly: {uuid}")`. (Features have their own finish phase.)
     - Any other lifecycle_class (`container_flow`, `brainstorm_flow`, `none`) → NOT in `_CLOSES_TERMINAL` → raise `InvalidCloseTargetError("complete_phase: lifecycle_class {lc} not closable via closes=: {uuid}")`.
  4. For each `uuid`: if current `status` is already terminal:
     - Check whether the prior closer matches: `SELECT from_uuid FROM entity_relations WHERE to_uuid=? AND kind='fixes' LIMIT 1`.
     - If returned `from_uuid == caller's from_uuid` → idempotent replay; SKIP all writes for this uuid (no update_entity, no phase_event append) and add the uuid to `closes_applied` in the response.
     - If returned `from_uuid != caller's from_uuid` (or no row exists) → raise `InvalidCloseTargetError("complete_phase: {uuid} already closed by different closer ({prior_from_uuid}); cannot re-close from {new_from_uuid}")` (or, when no entity_relations row exists, "already terminal but no closer record").
  5. Standard `complete_phase` work for the caller: phase transition + projection trigger.
  6. For each `uuid` NOT skipped in step 4 (i.e., not an idempotent replay): `update_entity(uuid, status=<derived_terminal>)` + `append_phase_event(type_id=<closed_entity_type_id>, event_type='entity_status_changed', metadata={"old_status": <prev>, "new_status": <derived_terminal>, "closed_by_uuid": <from_uuid>})`. (Skipping on replay avoids duplicate audit-trail events.)
  7. For each `uuid`: `INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) VALUES (<from_uuid>, <uuid>, 'fixes', <ISO_TS>) ON CONFLICT DO NOTHING`. The `ON CONFLICT DO NOTHING` makes the INSERT idempotent on the composite UNIQUE (FR-10.5). Replay path falls through cleanly.
  8. COMMIT.
- **FR-10.4 — Failure semantics.** If ANY closed-uuid (a) does not exist, (b) is already in a terminal state AND the prior closer differs from the current caller (or no `entity_relations` closer record exists per FR-10.3 step 4), (c) has an incompatible `lifecycle_class` per FR-10.3 step 3, (d) resides in a different workspace than the caller per FR-10.3 step 2, → entire transaction rolls back. complete_phase's primary effect (phase transition) is also reverted. Caller sees a clean failure (no partial state). **Exception (idempotent replay):** When the prior closer matches the current caller (same `from_uuid`), per FR-10.3 step 4 + FR-10.5, this is NOT a failure — writes are SKIPPED for that uuid and the response includes it in `closes_applied`.
- **FR-10.5 — Idempotency on replay.** Calling `complete_phase(phase='finish', closes=[u1])` after a previous successful call with the same closure set must succeed cleanly. Per FR-10.3 step 4, when the same closer replays, step 6 (update_entity + phase_event append) is SKIPPED for that uuid — preventing duplicate `entity_status_changed` audit events. INSERT in step 7 falls through via ON CONFLICT DO NOTHING. Concretely:
  - First call: transitions u1 → closed (or 'dropped' for backlog); appends 1 phase_event; INSERTs 1 entity_relations row; returns `closes_applied=[u1]`.
  - Second call (same from_uuid): step 4 detects same-closer, skips step 6; step 7 INSERT is no-op (ON CONFLICT); returns `closes_applied=[u1]`. Post-state: exactly 1 phase_event row + 1 entity_relations row for this (from, to, fixes) tuple.
  - Third call from a DIFFERENT from_uuid against u1 (already closed by from_uuid_1) → step 4 raises `InvalidCloseTargetError("complete_phase: u1 already closed by different closer ...")`. Transaction rolls back.
- **FR-10.6 — Returns.** Returns the standard complete_phase JSON response augmented with `closes_applied: [...]` field listing the uuids that were closed in this call (empty list if `closes=None` or `closes=[]`). On idempotent replay, `closes_applied` contains the uuids that were already closed by this from_uuid (no error).

### FR-relations-table — Migration 14: `entity_relations` table + CHECK widening

- **FR-MR.1 — `entity_relations` table.** Migration 14 creates:
  ```sql
  CREATE TABLE entity_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_uuid TEXT NOT NULL,
    to_uuid TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('fixes')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (from_uuid) REFERENCES entities(uuid) ON DELETE CASCADE,
    FOREIGN KEY (to_uuid) REFERENCES entities(uuid) ON DELETE CASCADE
  );
  CREATE UNIQUE INDEX idx_entity_relations_unique
    ON entity_relations(from_uuid, to_uuid, kind);
  CREATE INDEX idx_entity_relations_from ON entity_relations(from_uuid);
  CREATE INDEX idx_entity_relations_to ON entity_relations(to_uuid);
  ```
  **CHECK is narrowed to `kind='fixes'` only.** Other relation kinds (`blocks`, `relates_to`, `duplicates`) are deferred to future migrations when an API surface needs them. No dead columns.
- **FR-MR.2 — Widen (type, kind) CHECK on entities.** Migration 14 performs a copy-rename of the `entities` table to widen the CHECK constraint:
  - **Before:** `(type='work' AND kind IN ('feature','backlog','initiative','objective','key_result','task'))`
  - **After:** `(type='work' AND kind IN ('feature','backlog','bug','initiative','objective','key_result','task'))`
  - **Ordering rule:** preserve existing migration-12 insertion order; new value `'bug'` is inserted between `'backlog'` and `'initiative'` (matches the work_kind hierarchy: production kinds first → forward-compat kinds second). AC-MR.2's substring assert pins this exact sequence — the implementation must match it literally.
  - Procedure: standard SQLite CHECK-mutation pattern (CREATE TABLE entities_new, INSERT ... SELECT, DROP TABLE entities, ALTER TABLE entities_new RENAME). Triggers and indices recreated post-rename per the migration-12 precedent (`database.py:3290+`).
- **FR-MR.3 — Widen phase_events.event_type CHECK.** Migration 14 also widens the phase_events.event_type CHECK to admit `'spawned_child'`:
  - **Before:** `('started','completed','skipped','backward','entity_created','entity_status_changed','entity_promoted')` (7 values, per `database.py:3402`).
  - **After:** `('started','completed','skipped','backward','entity_created','entity_status_changed','entity_promoted','spawned_child')` (8 values).
  - Procedure: same copy-rename pattern as migration-12 (`database.py:3395+`).
- **FR-MR.4 — Extend `VALID_ENTITY_TYPES`.** The Python constant at `database.py:4534` extends to 9 values: add `'bug'`.
- **FR-MR.5 — Extend `register_entity` entity_type → (type, kind, lifecycle_class) mapping.** Add `'bug' → ('work', 'bug', 'bug_flow')` AND remap `'task' → ('work', 'task', 'task_flow')` (was `('work', 'task', 'work_flow')` per migration-12 backfill — the task remap aligns the lifecycle_class with the status-only model per FR-BL). If existing rows in the live DB have `kind='task'` with `lifecycle_class='work_flow'`, Migration 14 includes a one-time UPDATE: `UPDATE entities SET lifecycle_class='task_flow' WHERE kind='task'`. Operationally a no-op per Pin I (0 task entities in production live DB); test fixtures exercise the remap path.
- **FR-MR.6 — Pre-flight gate.** Migration 14 pre-flight asserts:
  - `schema_version = 13` (else abort: "Migration 14 requires schema_version=13; current={n}. Run prior migrations first.")
  - `entity_display` table present (else abort: "Migration 14 requires entity_display table (feature 110). Run feature-110 deferred remediation.")
  - `migration_audit_log` table present (else abort: same).
  - `entity_relations` table ABSENT (else abort: "Migration 14 entity_relations table already exists. Drop or replay-detect.").
- **FR-MR.7 — Down-migration `MIGRATIONS_DOWN[14]`.** Drops `entity_relations` + 3 indices. Reverses (type, kind) CHECK widening (copy-rename back to 6 work-kinds). Reverses phase_events.event_type CHECK widening (copy-rename back to 7 event_types) — **but only after first DELETING phase_events rows where event_type='spawned_child'** (else the copy-INSERT-SELECT into the narrower CHECK table fails). Reverts the lifecycle_class remap: `UPDATE entities SET lifecycle_class='work_flow' WHERE kind='task' AND lifecycle_class='task_flow'`. **Python constants `VALID_ENTITY_TYPES` and the `register_entity` entity_type → triple mapping are NOT reverted by the Python down-migration function** — they live in source code and are reverted only by reverting the feature 111 commit. The `MIGRATIONS_DOWN[14]` docstring documents this explicitly: "Caller must additionally revert source-code changes to VALID_ENTITY_TYPES and register_entity._ENTITY_TYPE_MAPPING to restore the v13 runtime contract." Same precedent as features 109/110 down-migrations (which similarly omit Python-constant reversion).
- **FR-MR.8 — Idempotency.** Replay-safe: re-running on schema_version=14 is a no-op. Single-transaction with foreign_key_check pre/post. PRAGMA foreign_keys MUST be ON throughout.
- **FR-MR.9 — Down-migration safety pre-flight.** `MIGRATIONS_DOWN[14]` MUST refuse to run if any `kind='bug'` entities exist or any `entity_relations` rows exist post-migration (CHECK widening narrowing back would fail mid-copy-rename). Procedure:
  ```
  bug_count = SELECT COUNT(*) FROM entities WHERE kind='bug'
  rel_count = SELECT COUNT(*) FROM entity_relations
  if bug_count > 0 OR rel_count > 0:
    raise MigrationError(
      f"Cannot down-migrate v14: {bug_count} bug entities + {rel_count} "
      "entity_relations exist. Delete or remap before down-migration."
    )
  ```
  Pre-flight runs BEFORE the destructive DELETE of `spawned_child` phase_events (FR-MR.7).

### FR-exceptions — New exception class definitions

- **FR-EX.1 — `EntityNotFoundError`.** Defined in `plugins/pd/hooks/lib/entity_registry/database.py` near `EntityExistsError` (currently around `:4484`). Subclasses `ValueError`. Constructor: `EntityNotFoundError(message: str)`. Raised by F10 closure transaction when caller's `type_id` resolves to no entity (FR-10.2) or closure target uuid resolves to no entity (FR-10.3 step 2).
- **FR-EX.2 — `InvalidCloseTargetError`.** Defined in same module, same pattern. Subclasses `ValueError`. Constructor: `InvalidCloseTargetError(message: str)`. Raised by F10 closure transaction for: incompatible lifecycle_class (FR-10.3 step 3), already-terminal with different closer (FR-10.3 step 4), already-terminal with no closer record (FR-10.3 step 4), cross-workspace closure attempt (FR-10.3 step 2).
- **FR-EX.3 — MCP layer translation.** At the `@mcp.tool()` boundary, both new exceptions are caught and translated to JSON error responses via the existing `_translate_error()` helper or equivalent pattern at `entity_server.py` / `workflow_state_server.py`. The error JSON shape: `{"error": true, "error_type": "<class_name_lowercased>", "message": "<exception_str>"}`.

### FR-cleanup — Free-text suffix parser removal

- **FR-CL.1 — `backfill.py:428` parser removal.** The block that parses `(closed:`, `(fixed:`, `(already implemented` markers is DELETED. The backfill logic that previously consumed it migrates to read `entities.status` and `entity_relations` rows directly. **Behavioral change is explicit:** historical free-text markers in retro/spec/backlog prose remain in their files (no rewrite); the parser no longer surfaces them. Any test asserting parsed-marker output is rewritten to assert DB-state output instead.
- **FR-CL.2 — `doctor/checks.py:991,995` parser removal.** Similar — delete the parsers; consume entity status from `entities.status` + `entity_relations`.
- **FR-CL.3 — Affected tests.**
  - `test_backfill.py:981, 992, 1037` — refactor to use DB-state input (synthetic entities with status='closed') instead of free-text marker input. If a test ONLY exercises the parser logic (no DB-state path), delete the test and replace with a positive doctor-lint test (AC-CL.1).
  - `test_entity_status.py:385-1168` — same triage; preserve fixtures that supply DB-state, delete fixtures that supply free-text-only.
- **FR-CL.4 — Doctor lint check.** Add a new doctor check (`check_no_free_text_status_parsers`) that runs `grep -rnE "\(closed:|\(promoted →|\(fixed:"` against absolute paths computed from `PROJECT_ROOT` (set by session-start; falls back to git rev-parse --show-toplevel if unset). The exact paths: `$PROJECT_ROOT/plugins/pd/hooks/lib/backfill.py` and `$PROJECT_ROOT/plugins/pd/hooks/lib/doctor/checks.py`. Returns FAIL if matches >0. The check is registered in `doctor/checks.py` and shows up in `/pd:doctor` output. Test fixtures and historical retros are out of scope (different paths). AC-CL.4 verifies the check runs correctly from at least two different CWDs (project root + an arbitrary subdirectory).

## §4 Acceptance Criteria

### AC-9.x — `issue_spawn`

- **AC-9.1** `issue_spawn(parent_uuid=<feature_uuid>, kind='bug', summary='Foo')` creates a `(type='work', kind='bug', lifecycle_class='bug_flow')` entity with `status='open'`, `parent_uuid=<feature_uuid>`, `entity_id` matching `^\d+-foo$`. Returns the new uuid. The `entity_display(entity_uuid, display_seq, display_slug)` row exists (1:1 invariant; AC-9.7).
- **AC-9.2** After issue_spawn, `SELECT workflow_phase, kanban_column FROM workflow_phases WHERE type_id=<parent_type_id>` returns the same tuple pre and post. `updated_at` is NOT asserted (may tick due to triggers).
- **AC-9.3** issue_spawn appends EXACTLY ONE phase_event on the parent with `event_type='spawned_child'`, `phase IS NULL`, `metadata` containing `{"child_uuid", "child_kind", "child_name"}`.
- **AC-9.4** Invalid kind (`kind='nonsense'`) raises `ValueError` BEFORE any DB write. Synthetic test: `SELECT COUNT(*)` for the workspace's `entities` and `phase_events` is byte-identical pre/post.
- **AC-9.5** Non-existent `parent_uuid` raises `ValueError("parent_not_found: ...")`; no partial state (entity not created, no phase_event appended). Parent with disallowed kind (e.g., `kind='brainstorm'`) raises `ValueError("invalid_parent_kind: ...")`; no partial state.
- **AC-9.6** issue_spawn-generated `entity_id` matches `^\d+-.+`; EntityIdFormatError cannot fire.
- **AC-9.7** `SELECT COUNT(*) FROM entity_display WHERE entity_uuid = <new_uuid>` returns exactly 1 with non-null `display_seq` (int) and non-null `display_slug` (string).
- **AC-9.8** `check_status_write_path` doctor check (AST-based per CLAUDE.md hook EPIPE/status discipline) PASSES on the issue_spawn implementation file (no direct phase_events INSERT).
- **AC-9.9** Caller-supplied metadata is shallow-merged into `entities.metadata` JSON with system-supplied keys winning. Synthetic test: caller passes `metadata={"severity": "high", "parent_uuid": "evil"}`; resulting `entities.metadata` JSON contains `severity='high'` AND does NOT contain a `parent_uuid` key (parent linkage lives in entities.parent_uuid column, not metadata).

### AC-10.x — `complete_phase(closes=)`

- **AC-10.1** `complete_phase(type_id='feature:111-issue-lifecycle-closure', phase='finish', closes=[u_bug, u_task])` transitions feature to `finish`, transitions `u_bug → status='closed'` and `u_task → status='closed'`, and writes 2 `entity_relations` rows in a single transaction. Verified: `SELECT COUNT(*) FROM entity_relations WHERE from_uuid = <feature_uuid> AND kind = 'fixes'` returns 2.
- **AC-10.2** `complete_phase(type_id=..., phase='finish')` without `closes` parameter behaves identically to pre-feature-111. Response JSON shape includes `closes_applied: []`.
- **AC-10.3** Atomic rollback: when one of `closes=[u1, u2]` fails the lifecycle_class check (e.g., u2 is a feature entity), the WHOLE transaction rolls back. Feature's phase remains the pre-call value; no entity_relations rows persisted; u1's status unchanged.
- **AC-10.4** Idempotent replay: calling `complete_phase(type_id=..., closes=[u1])` exactly **3 times** (same from_uuid, same to_uuid) succeeds all 3 times; final state has EXACTLY 1 `entity_relations` row (UNIQUE constraint via ON CONFLICT DO NOTHING); EXACTLY 1 `entity_status_changed` phase_event row for u1 (step 6 skip on replay); u1's status='closed' after each call; response `closes_applied=[u1]` after each call. `SELECT COUNT(*) FROM phase_events WHERE type_id=<u1_type_id> AND event_type='entity_status_changed'` returns 1 (not 3).
- **AC-10.5** Cross-closer conflict: u1 closed by feature_A, then `complete_phase(type_id='feature:B', closes=[u1])` raises `InvalidCloseTargetError` whose message contains the substring `'already closed by different closer'`. Transaction rolls back (feature_B's phase unchanged; no new entity_relations row).
- **AC-10.6** Cross-workspace closure forbidden: caller in workspace_A attempts `complete_phase(closes=[u_in_ws_B])` raises `InvalidCloseTargetError` with message substring `'cross-workspace closure forbidden'`. No partial state.
- **AC-10.7** Terminal-without-closer-record path: u1 manually transitioned to 'closed' via direct `update_entity(u1, status='closed')` (no closes= path used; no `entity_relations` row exists). A subsequent `complete_phase(closes=[u1])` from feature_X raises `InvalidCloseTargetError` whose message contains substring `'already terminal but no closer record'`. Transaction rolls back.
- **AC-10.8** Closed entities receive an `entity_status_changed` phase_event with metadata `{"old_status": "open", "new_status": "closed", "closed_by_uuid": <feature_uuid>}`.
- **AC-10.9** Caller-not-registered: `complete_phase(type_id='feature:nonexistent', phase='finish', closes=[u1])` raises `EntityNotFoundError` BEFORE any writes. No phase transition, no closure rows.
- **AC-10.10** `complete_phase(type_id=..., closes=[u_feature])` where `u_feature.lifecycle_class='feature_flow'` raises `InvalidCloseTargetError` (features cannot be closed via closes=).
- **AC-10.11** State-machine bypass: A backlog row at `status='open'` (NOT 'triaged') closed via `closes=[backlog_uuid]` transitions directly to `status='dropped'` (skipping 'triaged'). The phase_event metadata records `old_status='open', new_status='dropped'`. This documents the intentional state-machine bypass for closes= (FR-10 atomicity prioritized over `ENTITY_MACHINES['backlog']` graph adherence).

### AC-MR.x — Migration 14 safety

- **AC-MR.1** Post-migration, `PRAGMA table_info(entity_relations)` returns columns matching FR-MR.1 schema. All 3 indices present per `sqlite_master`. CHECK constraint admits `kind='fixes'` only.
- **AC-MR.2** Post-migration, `SELECT sql FROM sqlite_master WHERE name='entities'` contains the substring `'feature','backlog','bug','initiative','objective','key_result','task'` (in that order, per FR-MR.2 after-state).
- **AC-MR.3** Post-migration, `SELECT sql FROM sqlite_master WHERE name='phase_events'` contains the substring `'spawned_child'`.
- **AC-MR.4** Pre-flight: synthetic stale-12 DB (entity_display absent) aborts migration with: "Migration 14 requires entity_display table (feature 110). Run feature-110 deferred remediation."
- **AC-MR.5** Pre-flight: synthetic DB where `entity_relations` already exists aborts with: "Migration 14 entity_relations table already exists. Drop or replay-detect."
- **AC-MR.6** Idempotency: replay on v14 DB is a no-op (schema_version unchanged at 14; no DDL fires).
- **AC-MR.7** Down-migration on a 50-row fixture (mix of entities + 10 entity_relations rows + 5 spawned_child phase_events) leaves `entities`, `workflow_phases`, AND `phase_events` (excluding rows with event_type='spawned_child') tables byte-identical to a pre-migration-14 snapshot (sqlite3 .dump compare per-table). Phase_events rows with `event_type='spawned_child'` are DELETED by the down-migration before the CHECK narrowing copy-rename; this destructive policy is documented in `MIGRATIONS_DOWN[14]` docstring. The lifecycle_class remap for `kind='task'` is also reverted (`task_flow` → `work_flow`). Post-down, `SELECT MAX(version) FROM schema_migrations` returns 13 (not 14); `.tables` does NOT include `entity_relations`.
- **AC-MR.8** Composite UNIQUE works: `INSERT INTO entity_relations(from='u1', to='u2', kind='fixes'); INSERT ... same values` — second INSERT fails with UNIQUE constraint error (when called WITHOUT ON CONFLICT DO NOTHING; the FR-10.3 step 7 code path uses ON CONFLICT DO NOTHING).
- **AC-MR.9** Post-migration, `PRAGMA foreign_keys = ON` is set; INSERT into `entity_relations` with a non-existent `from_uuid` raises FK violation.
- **AC-MR.10** Down-migration pre-flight: synthetic v14 DB with 1 bug entity present → `MIGRATIONS_DOWN[14]` raises `MigrationError` whose message contains substring `"Cannot down-migrate v14"` and `"bug entities"`. No partial down-migration state.
- **AC-MR.11** Down-migration pre-flight: synthetic v14 DB with 0 bug entities but 3 entity_relations rows present → raises with substring `"entity_relations"`. No partial down-migration state.

### AC-EX.x — New exception classes

- **AC-EX.1** `from entity_registry.database import EntityNotFoundError, InvalidCloseTargetError` succeeds. Both are subclasses of `ValueError`.
- **AC-EX.2** Raising and catching the new exceptions works through the MCP `@mcp.tool()` boundary: `complete_phase(type_id='feature:nonexistent', closes=[u1])` returns JSON `{"error": true, "error_type": "entitynotfounderror", "message": "complete_phase: caller not registered: feature:nonexistent"}` (or equivalent error envelope per existing `_translate_error` pattern).

### AC-BL.x — Status-only lifecycle for bug/task

- **AC-BL.1** `ENTITY_MACHINES` dict does NOT contain keys `'bug'` or `'task'`. (Introspection-only assertion.)
- **AC-BL.2** `_KIND_TO_TYPE_LIFECYCLE['bug']` returns `('work', 'bug_flow')`. `_KIND_TO_TYPE_LIFECYCLE['task']` returns `('work', 'task_flow')`.
- **AC-BL.3** `_CLOSES_TERMINAL['bug_flow']` returns `'closed'`. `_CLOSES_TERMINAL['task_flow']` returns `'closed'`. `_CLOSES_TERMINAL['work_flow']` returns `'dropped'`. `'feature_flow'`, `'brainstorm_flow'`, `'container_flow'` are NOT keys in `_CLOSES_TERMINAL`.
- **AC-BL.4** After `issue_spawn(parent_uuid, kind='bug', summary='X')`: `SELECT type, kind, lifecycle_class, status FROM entities WHERE uuid=<new>` returns `('work', 'bug', 'bug_flow', 'open')`. NO row exists in `workflow_phases` for the new entity's type_id.
- **AC-BL.5** Direct `db.update_entity(bug_uuid, status='resolved')` succeeds (entities.status has no CHECK; status-only model accepts the write). `SELECT status FROM entities WHERE uuid=<bug>` returns `'resolved'`. No workflow_phases write occurs.
- **AC-BL.6** `complete_phase(closes=[bug_uuid])` on a status='open' bug transitions to status='closed' AND writes entity_relations row (per AC-10.x). The bug does NOT gain a workflow_phases row mid-closure.
- **AC-BL.7** Calling `transition_entity_phase(type_id='bug:X', ...)` raises (no ENTITY_MACHINES entry → first-line validation fails with KeyError or invalid_entity_type — implementation choice; design phase pins exact error). This is a defensive AC to confirm bug entities are not accidentally routed through the state-machine path.

### AC-CL.x — Free-text suffix parser cleanup

- **AC-CL.1** `grep -rnE "\(closed:|\(promoted →|\(fixed:" plugins/pd/hooks/lib/backfill.py plugins/pd/hooks/lib/doctor/checks.py` returns 0 matches. (Test files and historical retro markdown are excluded from this lint scope.)
- **AC-CL.2** Backfill behavioral change documented: backfill no longer surfaces historically-prose-marked closures. The behavioral delta is explicit in the doctor output schema (`backfill_status_source: 'db'` post-feature-111 vs `'mixed'` pre-feature-111). No automated migration of historical prose markers into `entity_relations` rows.
- **AC-CL.3** Doctor `check_backlog_promotions` (or its successor) reads from DB: synthetic backlog row with `status='dropped'` and `entity_relations(from=<feature_uuid>, to=<backlog_uuid>, kind='fixes')` is correctly identified by doctor as "closed by feature_X". No free-text parsing involved in this code path.
- **AC-CL.4** New doctor check `check_no_free_text_status_parsers` PASSES on production code (grep returns 0); FAILS on a synthetic regression where a parser is re-introduced. The check produces the SAME result when run from the project root AND from a subdirectory (e.g., `cd plugins/pd/hooks && python -m doctor.checks check_no_free_text_status_parsers`) — pins the PROJECT_ROOT / `git rev-parse --show-toplevel` fallback in FR-CL.4.

## §5 Non-Functional Requirements

- **NFR-1 — Atomic commit discipline.** Each Group (sub-feature) is its own commit. F9, F10, Migration 14 DDL, ENTITY_MACHINES['bug'], cleanup do NOT share commits. Per knowledge-bank pattern: schema migration commit MUST contain the migration only — no co-located logic changes.
- **NFR-2 — No new third-party dependencies.** Stdlib + existing project deps only.
- **NFR-3 — Bash 3.2 / macOS BSD portability** for any new shell helpers (none expected).
- **NFR-4 — Hook EPIPE safety** — N/A this feature (no new hooks).
- **NFR-5 — Idempotent migrations** per AC-MR.6.
- **NFR-6 — Doctor check_status_write_path AST scan PASSES on all new code** (FR-9.8).

## §6 Out of Scope (Deferred)

- Additional relation kinds beyond `kind='fixes'` (e.g., `blocks`, `relates_to`, `duplicates`) — future migration when an API surface needs them. CHECK is narrowed to `'fixes'` only to avoid dead columns.
- `issue_spawn` from `brainstorm`/`workspace`/`bug`/`task` parents — restricted at FR-9.6 (raises `invalid_parent_kind`). Allowed parent kinds: `{feature, backlog, project}`. Further parent-kind expansion is out of scope.
- Issue terminal-state transitions BEYOND `closed` via `complete_phase(closes=)` (e.g., bug → 'resolved' or → 'wont_fix') — these go through `update_entity` directly or future MCP. closes= hardcodes `closed`.
- Bulk closure CLI / `/pd:close` command — separate feature.
- Renaming `complete_phase` to better reflect the closes= surface — naming bikeshed deferred.
- Backfill of historical free-text `(closed: ...)` markers into `entity_relations` rows — explicitly out of scope per FR-CL.1 and AC-CL.2. Historical prose remains in files.
- Cross-workspace closure linkage — explicitly FORBIDDEN at application layer per FR-10.2 and FR-10.3 step 2; AC-10.6 asserts the raise. (Schema-level enforcement via FK is not added in this feature; the application-layer check is sufficient because all writes route through the MCP surface.)

## §7 Open Risks

- **R1 — (type, kind) CHECK copy-rename complexity.** The migration-12 precedent at `database.py:3290+` shows the copy-rename procedure is non-trivial (drop indices, drop triggers, recreate post-rename). Migration 14 must replicate this carefully for both `entities` AND `phase_events`. Design phase enumerates exact trigger/index list to recreate.
- **R2 — `bug_flow`/`task_flow` lifecycle_class blast radius.** Expected blast-radius files from spec-time grep: `entity_engine.py` routing (currently keys on `type='container'`; lifecycle_class enumeration not expected here but design phase confirms); `doctor/checks.py` (no `check_lifecycle_class_valid` currently exists — design phase verifies). Design phase confirms these are the only sites, adds bug_flow/task_flow handling, and verifies `grep -nE "lifecycle_class\s*==\s*'|LIFECYCLE_CLASS_" plugins/pd/` returns 0 unhandled enumeration sites post-implementation.
- **R3 — Cleanup blast radius.** Removing free-text suffix parsers may break tests that read parser output. Conservative estimate from §1.1 row "Free-text suffix parsers": ~10 tests affected. Implement may need to migrate fixtures rather than delete.
- **R4 — Idempotency-on-replay vs strict-atomic semantics.** FR-10.5 chooses idempotency-on-same-closer (ON CONFLICT DO NOTHING + closer-match check). Alternative was strict-atomic (any duplicate rolls back). Trade-off: idempotency is operationally safer for retries but loses error visibility on accidental double-close. Spec defaults to idempotency-on-same-closer.
- **R5 — Idle-trigger touch of parent row.** AC-9.2 asserts column-level invariance of `workflow_phase` AND `kanban_column`, but `updated_at` may legitimately tick if any trigger fires on a parent-row write. Implementation must avoid spurious touches of the parent `workflow_phases` row when only appending a phase_event; design phase greps for triggers on `workflow_phases` table that may fire on insert into `phase_events`.
- **R6 — Caller uuid stability across workspace re-registration.** The idempotency check in FR-10.3 step 4 matches `entity_relations.from_uuid` against the current caller's resolved `from_uuid`. If the calling feature is re-registered with a new uuid (e.g., after a workspace migration or manual DB surgery), a prior `entity_relations` row written under the old uuid will not match and will be treated as a different-closer conflict. This is acceptable given workspace-uuid stability guarantees from feature 109; no additional handling required, but design phase notes the edge case in implementation comments.

## §8 Verification Mapping

| AC | Verification mechanism | Test file |
|---|---|---|
| AC-9.x | DB introspection + phase_events query + entity_display 1:1 check | `test_issue_spawn.py` (new) |
| AC-10.x | Multi-call orchestration + entity_relations query + idempotency replay + cross-closer | `test_complete_phase_closes.py` (new) |
| AC-MR.x | Migration runner + PRAGMA + sqlite_master string assert + dump-compare + FK enforcement | `test_migration_14_safety.py` (new) |
| AC-BL.x | Dict introspection + status-only model verification + workflow_phases absence checks | `test_entity_lifecycle.py` + `test_status_only_lifecycle.py` (new) |
| AC-CL.x | grep lint + doctor check assertion + DB-state regression | `test_cleanup_suffix_parsers.py` (new) + `test_doctor.py` (extended) |
