# Feature 111 — Issue Lifecycle Closure

- **Project:** P003-entity-system-redesign — Milestone M4 (Phase 4 — Lifecycle Closure) — final feature in P003
- **Depends on:** 109-polymorphic-taxonomy-and-event (post-migration-12 baseline; `entity_type` column DROPPED, `type`/`kind`/`lifecycle_class` triple ACTIVE); 110-markdown-projections-and-gener (post-migration-13 `entity_display` + projection sealed write path)
- **Brainstorm source:** `docs/projects/P003-entity-system-redesign/prd.md`
- **Status:** revision 2 (addresses iter-1 spec-reviewer blockers around taxonomy reconciliation, terminal-state derivation, feature_uuid resolution, and backfill contradiction)

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
- **Pin G — Free-text parsers present:** `grep -nE "(closed:|fixed:|promoted →)" plugins/pd/hooks/lib/backfill.py plugins/pd/hooks/lib/doctor/checks.py` returns ≥4 hits (the parser sites). Post-feature-111, this returns 0 hits.

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
- **FR-9.2 — Entity creation contract.** `issue_spawn` calls `register_entity(entity_type=kind, entity_id=<auto>, name=summary, parent_uuid=parent_uuid, status='open', workspace_uuid=..., metadata=metadata)`. The `entity_id` is generated via `id_generator.generate_entity_id(_db, kind, name, project_id)` (auto_id path) — produces conformant `{seq}-{slug}` so EntityIdFormatError cannot fire. The internal `entity_type → (type, kind, lifecycle_class)` mapping in register_entity is extended: `kind='bug' → (type='work', kind='bug', lifecycle_class='bug_flow')`; `kind='task' → (type='work', kind='task', lifecycle_class='work_flow')` (matches existing task fixture pattern).
- **FR-9.3 — Parent phase_event append.** After entity creation, `issue_spawn` MUST `append_phase_event(type_id=<parent_type_id>, event_type='spawned_child', phase=NULL, metadata={"child_uuid": <new_uuid>, "child_kind": kind, "child_name": summary})`. The parent's `workflow_phases.workflow_phase` AND `workflow_phases.kanban_column` are NOT modified — strict byte-identical pre/post.
- **FR-9.4 — Returns.** Returns the new entity uuid (string).
- **FR-9.5 — kind enum.** `kind` value MUST be one of `{"bug", "task"}` (per PRD Story 8 `work.kind` ontology). Invalid kind raises `ValueError` BEFORE any DB write.
- **FR-9.6 — Parent existence check.** `parent_uuid` MUST resolve to an existing entity row in the same workspace (within the resolved `workspace_uuid`). If not, raise `ValueError("parent_not_found: {parent_uuid}")` BEFORE any DB write. No partial state created.
- **FR-9.7 — entity_display 1:1 invariant.** Per feature 110's invariant, every `register_entity` write atomically produces an `entity_display(entity_uuid, display_seq, display_slug)` row. issue_spawn inherits this — no additional plumbing needed. AC-9.7 verifies the row exists post-call.
- **FR-9.8 — Doctor check_status_write_path compliance.** issue_spawn implementation MUST go through `append_phase_event()` for the parent event (no direct INSERT into phase_events). The AST-based doctor check (`check_status_write_path`) MUST pass on the new code.

### FR-bug-machine — entity_lifecycle.py 'bug' state machine

- **FR-BM.1 — `ENTITY_MACHINES['bug']` added.** State graph:
  - States: `open` (initial), `resolved`, `closed`, `wont_fix` (all 3 terminal).
  - Transitions: `open → resolved`, `open → closed`, `open → wont_fix`. No transitions FROM terminal states.
  - Columns mapping (kanban): all 4 states map to existing kanban_column values — `open → 'wip'`, `resolved → 'completed'`, `closed → 'completed'`, `wont_fix → 'completed'`. (kanban_column CHECK at `database.py:743` already admits these; no widening needed.)
- **FR-BM.2 — Forward-set shape.** `ENTITY_MACHINES['bug']['forward']` is a set of (from, to) tuples matching the brainstorm/backlog convention (`entity_lifecycle.py:28-34`, `:48-53`):
  ```python
  "forward": {
      ("open", "resolved"),
      ("open", "closed"),
      ("open", "wont_fix"),
  }
  ```
- **FR-BM.3 — `task` lifecycle.** kind='task' uses the existing 'work_flow' lifecycle_class for back-compat with existing test fixtures. No new ENTITY_MACHINES entry for 'task' in this feature. Terminal state for task = 'closed' (matches the closes= caller pattern).

### FR-10 — `complete_phase(closes=[uuid...])` atomic closure

- **FR-10.1 — Signature extension.** Both `workflow_state_server.py:1809` (MCP tool) and `_process_complete_phase` at `:1086` (internal dispatcher) gain a new optional kwarg:
  ```python
  closes: list[str] | None = None  # list of entity uuids to atomically close
  ```
  - `closes=None` (default) → existing behavior (no closure linkage).
  - `closes=[]` → no-op for closure (empty list, no rows written), but the rest of complete_phase runs normally.
- **FR-10.2 — Calling-entity uuid resolution.** `_process_complete_phase` resolves the calling entity's uuid via `SELECT uuid FROM entities WHERE workspace_uuid=? AND type_id=?` at the **start of the transaction** (before any writes). If lookup fails, raise `EntityNotFoundError("complete_phase: caller not registered: {type_id}")`. This `from_uuid` is used as `entity_relations.from_uuid` for all rows written in step 4 below.
- **FR-10.3 — Atomic transaction order.** When `closes` is non-empty, the entire `complete_phase` operation runs in a single `BEGIN IMMEDIATE` transaction. Order:
  1. Resolve calling entity's `from_uuid` (FR-10.2).
  2. For each `uuid` in `closes`: `SELECT type, kind, lifecycle_class, status FROM entities WHERE uuid = ?`. If row missing → raise `EntityNotFoundError`.
  3. For each closed entity, **derive terminal state from its `lifecycle_class`**:
     - `lifecycle_class='bug_flow'` (kind='bug') → terminal = `'closed'` (callers wanting 'resolved'/'wont_fix' use `update_entity` directly; `closes=` is for "this feature fixed this bug" only).
     - `lifecycle_class='work_flow'` (kind='backlog' or 'task') → terminal = `'dropped'` for backlog, `'closed'` for task. (Use a small lookup map: `{(kind='backlog'): 'dropped', (kind='task'): 'closed'}`.)
     - `lifecycle_class='feature_flow'` → NOT supported. Raise `InvalidCloseTargetError("complete_phase: feature entities cannot be closed via closes=; use complete_phase('finish') directly: {uuid}")`. (Features have their own finish phase.)
     - Other lifecycle_classes → raise `InvalidCloseTargetError`.
  4. For each `uuid`: if current `status` is already terminal → raise `InvalidCloseTargetError("complete_phase: {uuid} already terminal ({status})")`. (Idempotency caveat: see FR-10.5.)
  5. Standard `complete_phase` work for the caller: phase transition + projection trigger.
  6. For each `uuid`: `update_entity(uuid, status=<derived_terminal>)` + `append_phase_event(type_id=<closed_entity_type_id>, event_type='entity_status_changed', metadata={"old_status": <prev>, "new_status": <derived_terminal>, "closed_by_uuid": <from_uuid>})`.
  7. For each `uuid`: `INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) VALUES (<from_uuid>, <uuid>, 'fixes', <ISO_TS>) ON CONFLICT DO NOTHING`. The `ON CONFLICT DO NOTHING` makes the INSERT idempotent on the composite UNIQUE (FR-10.5).
  8. COMMIT.
- **FR-10.4 — Failure semantics.** If ANY closed-uuid (a) does not exist, (b) is already in a terminal state, (c) has an incompatible `lifecycle_class` per FR-10.3 step 3, → entire transaction rolls back. complete_phase's primary effect (phase transition) is also reverted. Caller sees a clean failure (no partial state).
- **FR-10.5 — Idempotency on replay.** Calling `complete_phase(phase='finish', closes=[u1])` after a previous successful call with the same closure set must succeed cleanly: `update_entity(u1, status='closed')` is a no-op when already closed (current behavior of update_entity); `ON CONFLICT DO NOTHING` skips the duplicate entity_relations row. The pre-flight check in FR-10.3 step 4 (`status already terminal → raise`) is **bypassed when the closer is the same as the prior closer** (verified by `SELECT from_uuid FROM entity_relations WHERE to_uuid=? AND kind='fixes'` returning the current `from_uuid`). Concretely:
  - First call: transitions u1 → closed; INSERT entity_relations(from, u1, fixes); succeeds.
  - Second call (same from_uuid): u1 already closed → skip FR-10.3 step 4 raise (because `SELECT from_uuid FROM entity_relations WHERE to_uuid=u1 AND kind='fixes'` returns the same from_uuid); INSERT ON CONFLICT DO NOTHING; succeeds.
  - Third call from a DIFFERENT from_uuid against u1 (which is already closed by from_uuid_1) → FR-10.3 step 4 raises because the new `from_uuid` doesn't match the prior closer.
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
  - Procedure: standard SQLite CHECK-mutation pattern (CREATE TABLE entities_new, INSERT ... SELECT, DROP TABLE entities, ALTER TABLE entities_new RENAME). Triggers and indices recreated post-rename per the migration-12 precedent (`database.py:3290+`).
- **FR-MR.3 — Widen phase_events.event_type CHECK.** Migration 14 also widens the phase_events.event_type CHECK to admit `'spawned_child'`:
  - **Before:** `('started','completed','skipped','backward','entity_created','entity_status_changed','entity_promoted')` (7 values, per `database.py:3402`).
  - **After:** `('started','completed','skipped','backward','entity_created','entity_status_changed','entity_promoted','spawned_child')` (8 values).
  - Procedure: same copy-rename pattern as migration-12 (`database.py:3395+`).
- **FR-MR.4 — Extend `VALID_ENTITY_TYPES`.** The Python constant at `database.py:4534` extends to 9 values: add `'bug'`.
- **FR-MR.5 — Extend `register_entity` entity_type → (type, kind, lifecycle_class) mapping.** Add the row `'bug' → ('work', 'bug', 'bug_flow')` to the internal mapping table used at `database.py:5188+`.
- **FR-MR.6 — Pre-flight gate.** Migration 14 pre-flight asserts:
  - `schema_version = 13` (else abort: "Migration 14 requires schema_version=13; current={n}. Run prior migrations first.")
  - `entity_display` table present (else abort: "Migration 14 requires entity_display table (feature 110). Run feature-110 deferred remediation.")
  - `migration_audit_log` table present (else abort: same).
  - `entity_relations` table ABSENT (else abort: "Migration 14 entity_relations table already exists. Drop or replay-detect.").
- **FR-MR.7 — Down-migration `MIGRATIONS_DOWN[14]`.** Drops `entity_relations` + 3 indices. Reverses (type, kind) CHECK widening (copy-rename back to 6 work-kinds). Reverses phase_events.event_type CHECK widening (copy-rename back to 7 event_types). Restores `VALID_ENTITY_TYPES` and register_entity mapping via git-history (Python source code, not runtime — same precedent as features 109/110 down-migrations).
- **FR-MR.8 — Idempotency.** Replay-safe: re-running on schema_version=14 is a no-op. Single-transaction with foreign_key_check pre/post. PRAGMA foreign_keys MUST be ON throughout.

### FR-cleanup — Free-text suffix parser removal

- **FR-CL.1 — `backfill.py:428` parser removal.** The block that parses `(closed:`, `(fixed:`, `(already implemented` markers is DELETED. The backfill logic that previously consumed it migrates to read `entities.status` and `entity_relations` rows directly. **Behavioral change is explicit:** historical free-text markers in retro/spec/backlog prose remain in their files (no rewrite); the parser no longer surfaces them. Any test asserting parsed-marker output is rewritten to assert DB-state output instead.
- **FR-CL.2 — `doctor/checks.py:991,995` parser removal.** Similar — delete the parsers; consume entity status from `entities.status` + `entity_relations`.
- **FR-CL.3 — Affected tests.**
  - `test_backfill.py:981, 992, 1037` — refactor to use DB-state input (synthetic entities with status='closed') instead of free-text marker input. If a test ONLY exercises the parser logic (no DB-state path), delete the test and replace with a positive doctor-lint test (AC-CL.1).
  - `test_entity_status.py:385-1168` — same triage; preserve fixtures that supply DB-state, delete fixtures that supply free-text-only.
- **FR-CL.4 — Doctor lint check.** Add a new doctor check (`check_no_free_text_status_parsers`) that runs `grep -rnE "\(closed:|\(promoted →|\(fixed:" plugins/pd/hooks/lib/backfill.py plugins/pd/hooks/lib/doctor/checks.py` and returns FAIL if matches >0. The check is registered in `doctor/checks.py` and shows up in `/pd:doctor` output. Test fixtures and historical retros are allowed to retain the strings (the lint scopes to production code paths only).

## §4 Acceptance Criteria

### AC-9.x — `issue_spawn`

- **AC-9.1** `issue_spawn(parent_uuid=<feature_uuid>, kind='bug', summary='Foo')` creates a `(type='work', kind='bug', lifecycle_class='bug_flow')` entity with `status='open'`, `parent_uuid=<feature_uuid>`, `entity_id` matching `^\d+-foo$`. Returns the new uuid. The `entity_display(entity_uuid, display_seq, display_slug)` row exists (1:1 invariant; AC-9.7).
- **AC-9.2** After issue_spawn, parent's `workflow_phases` row is byte-identical pre/post except (potentially) `updated_at`. Specifically: `workflow_phase` and `kanban_column` columns are unchanged.
- **AC-9.3** issue_spawn appends EXACTLY ONE phase_event on the parent with `event_type='spawned_child'`, `phase IS NULL`, `metadata` containing `{"child_uuid", "child_kind", "child_name"}`.
- **AC-9.4** Invalid kind (`kind='nonsense'`) raises `ValueError` BEFORE any DB write. Synthetic test: `SELECT COUNT(*)` for the workspace's `entities` and `phase_events` is byte-identical pre/post.
- **AC-9.5** Non-existent `parent_uuid` raises `ValueError("parent_not_found: ...")`; no partial state (entity not created, no phase_event appended).
- **AC-9.6** issue_spawn-generated `entity_id` matches `^\d+-.+`; EntityIdFormatError cannot fire.
- **AC-9.7** `SELECT COUNT(*) FROM entity_display WHERE entity_uuid = <new_uuid>` returns exactly 1 with non-null `display_seq` (int) and non-null `display_slug` (string).
- **AC-9.8** `check_status_write_path` doctor check (AST-based per CLAUDE.md hook EPIPE/status discipline) PASSES on the issue_spawn implementation file (no direct phase_events INSERT).
- **AC-9.9** Caller can supply `metadata={"severity": "high"}`; the dict is merged into `entities.metadata` JSON (not the phase_event's metadata).

### AC-10.x — `complete_phase(closes=)`

- **AC-10.1** `complete_phase(type_id='feature:111-issue-lifecycle-closure', phase='finish', closes=[u_bug, u_task])` transitions feature to `finish`, transitions `u_bug → status='closed'` and `u_task → status='closed'`, and writes 2 `entity_relations` rows in a single transaction. Verified: `SELECT COUNT(*) FROM entity_relations WHERE from_uuid = <feature_uuid> AND kind = 'fixes'` returns 2.
- **AC-10.2** `complete_phase(type_id=..., phase='finish')` without `closes` parameter behaves identically to pre-feature-111. Response JSON shape includes `closes_applied: []`.
- **AC-10.3** Atomic rollback: when one of `closes=[u1, u2]` fails the lifecycle_class check (e.g., u2 is a feature entity), the WHOLE transaction rolls back. Feature's phase remains the pre-call value; no entity_relations rows persisted; u1's status unchanged.
- **AC-10.4** Idempotent replay: calling `complete_phase(type_id=..., closes=[u1])` twice (same from_uuid, same to_uuid) succeeds both times; final state has 1 `entity_relations` row (UNIQUE constraint via ON CONFLICT DO NOTHING); u1's status='closed' both times; response `closes_applied=[u1]` both times.
- **AC-10.5** Cross-closer conflict: u1 closed by feature_A, then `complete_phase(type_id='feature:B', closes=[u1])` raises `InvalidCloseTargetError` because u1 is already terminal AND the new from_uuid is not the prior closer. Transaction rolls back.
- **AC-10.6** Closed entities receive an `entity_status_changed` phase_event with metadata `{"old_status": "open", "new_status": "closed", "closed_by_uuid": <feature_uuid>}`.
- **AC-10.7** Caller-not-registered: `complete_phase(type_id='feature:nonexistent', phase='finish', closes=[u1])` raises `EntityNotFoundError` BEFORE any writes. No phase transition, no closure rows.
- **AC-10.8** `complete_phase(type_id=..., closes=[u_feature])` where `u_feature.lifecycle_class='feature_flow'` raises `InvalidCloseTargetError` (features cannot be closed via closes=).

### AC-MR.x — Migration 14 safety

- **AC-MR.1** Post-migration, `PRAGMA table_info(entity_relations)` returns columns matching FR-MR.1 schema. All 3 indices present per `sqlite_master`. CHECK constraint admits `kind='fixes'` only.
- **AC-MR.2** Post-migration, `SELECT sql FROM sqlite_master WHERE name='entities'` contains the substring `'feature','backlog','bug','initiative','objective','key_result','task'` (in that order, per FR-MR.2 after-state).
- **AC-MR.3** Post-migration, `SELECT sql FROM sqlite_master WHERE name='phase_events'` contains the substring `'spawned_child'`.
- **AC-MR.4** Pre-flight: synthetic stale-12 DB (entity_display absent) aborts migration with: "Migration 14 requires entity_display table (feature 110). Run feature-110 deferred remediation."
- **AC-MR.5** Pre-flight: synthetic DB where `entity_relations` already exists aborts with: "Migration 14 entity_relations table already exists. Drop or replay-detect."
- **AC-MR.6** Idempotency: replay on v14 DB is a no-op (schema_version unchanged at 14; no DDL fires).
- **AC-MR.7** Down-migration on a 50-row fixture (mix of entities + 10 entity_relations rows + 5 spawned_child phase_events) leaves `entities` and `workflow_phases` tables byte-identical to a pre-migration-14 snapshot (sqlite3 .dump compare). Phase_events rows with `event_type='spawned_child'` MUST be dropped or rejected (CHECK violation post-down) — down-migration policy: delete spawned_child rows before narrowing CHECK.
- **AC-MR.8** Composite UNIQUE works: `INSERT INTO entity_relations(from='u1', to='u2', kind='fixes'); INSERT ... same values` — second INSERT fails with UNIQUE constraint error (when called WITHOUT ON CONFLICT DO NOTHING; the FR-10.7 code path uses ON CONFLICT DO NOTHING).
- **AC-MR.9** Post-migration, `PRAGMA foreign_keys = ON` is set; INSERT into `entity_relations` with a non-existent `from_uuid` raises FK violation.

### AC-BM.x — `entity_lifecycle.ENTITY_MACHINES['bug']`

- **AC-BM.1** `ENTITY_MACHINES['bug']` exists with 4 states (open, resolved, closed, wont_fix). All 3 forward transitions FROM 'open' present. 0 transitions FROM terminal states.
- **AC-BM.2** Synthetic `transition_entity_phase(type_id='bug:X', workflow_phase='resolved', kanban_column='completed')` from 'open' succeeds.
- **AC-BM.3** Synthetic `transition_entity_phase(type_id='bug:X', workflow_phase='open', ...)` FROM 'resolved' raises `invalid_transition` (no terminal→non-terminal).
- **AC-BM.4** Synthetic `transition_entity_phase(type_id='bug:X', workflow_phase='nonsense', ...)` raises `invalid_transition: nonsense is not a valid phase for bug`.

### AC-CL.x — Free-text suffix parser cleanup

- **AC-CL.1** `grep -rnE "\(closed:|\(promoted →|\(fixed:" plugins/pd/hooks/lib/backfill.py plugins/pd/hooks/lib/doctor/checks.py` returns 0 matches. (Test files and historical retro markdown are excluded from this lint scope.)
- **AC-CL.2** Backfill behavioral change documented: backfill no longer surfaces historically-prose-marked closures. The behavioral delta is explicit in the doctor output schema (`backfill_status_source: 'db'` post-feature-111 vs `'mixed'` pre-feature-111). No automated migration of historical prose markers into `entity_relations` rows.
- **AC-CL.3** Doctor `check_backlog_promotions` (or its successor) reads from DB: synthetic backlog row with `status='dropped'` and `entity_relations(from=<feature_uuid>, to=<backlog_uuid>, kind='fixes')` is correctly identified by doctor as "closed by feature_X". No free-text parsing involved in this code path.
- **AC-CL.4** New doctor check `check_no_free_text_status_parsers` PASSES on production code (grep returns 0); FAILS on a synthetic regression where a parser is re-introduced.

## §5 Non-Functional Requirements

- **NFR-1 — Atomic commit discipline.** Each Group (sub-feature) is its own commit. F9, F10, Migration 14 DDL, ENTITY_MACHINES['bug'], cleanup do NOT share commits. Per knowledge-bank pattern: schema migration commit MUST contain the migration only — no co-located logic changes.
- **NFR-2 — No new third-party dependencies.** Stdlib + existing project deps only.
- **NFR-3 — Bash 3.2 / macOS BSD portability** for any new shell helpers (none expected).
- **NFR-4 — Hook EPIPE safety** — N/A this feature (no new hooks).
- **NFR-5 — Idempotent migrations** per AC-MR.6.
- **NFR-6 — Doctor check_status_write_path AST scan PASSES on all new code** (FR-9.8).

## §6 Out of Scope (Deferred)

- Additional relation kinds beyond `kind='fixes'` (e.g., `blocks`, `relates_to`, `duplicates`) — future migration when an API surface needs them. CHECK is narrowed to `'fixes'` only to avoid dead columns.
- `issue_spawn` from non-feature parents (e.g., backlog rows or projects) — design phase decides whether to support or restrict; spec defaults to feature-parent only via FR-9.6 parent-existence check (but does not restrict by parent kind).
- Issue terminal-state transitions BEYOND `closed` via `complete_phase(closes=)` (e.g., bug → 'resolved' or → 'wont_fix') — these go through `update_entity` directly or future MCP. closes= hardcodes `closed`.
- Bulk closure CLI / `/pd:close` command — separate feature.
- Renaming `complete_phase` to better reflect the closes= surface — naming bikeshed deferred.
- Backfill of historical free-text `(closed: ...)` markers into `entity_relations` rows — explicitly out of scope per FR-CL.1 and AC-CL.2. Historical prose remains in files.
- Cross-workspace closure linkage (i.e., a feature in workspace A closes a backlog row in workspace B) — `entity_relations` schema does not enforce workspace boundary at SQL level; design phase decides whether to add an application-layer check.

## §7 Open Risks

- **R1 — (type, kind) CHECK copy-rename complexity.** The migration-12 precedent at `database.py:3290+` shows the copy-rename procedure is non-trivial (drop indices, drop triggers, recreate post-rename). Migration 14 must replicate this carefully for both `entities` AND `phase_events`. Design phase enumerates exact trigger/index list to recreate.
- **R2 — `bug_flow` lifecycle_class.** Introducing a new lifecycle_class value requires checking whether any downstream code enumerates lifecycle_classes (e.g., entity_engine routing, doctor checks). Design phase greps for `lifecycle_class\s*==\s*'` and `LIFECYCLE_CLASS_` constants.
- **R3 — Cleanup blast radius.** Removing free-text suffix parsers may break tests that read parser output. Conservative estimate from §1.1 row "Free-text suffix parsers": ~10 tests affected. Implement may need to migrate fixtures rather than delete.
- **R4 — Idempotency-on-replay vs strict-atomic semantics.** FR-10.5 chooses idempotency-on-same-closer (ON CONFLICT DO NOTHING + closer-match check). Alternative was strict-atomic (any duplicate rolls back). Trade-off: idempotency is operationally safer for retries but loses error visibility on accidental double-close. Spec defaults to idempotency-on-same-closer.
- **R5 — kanban_column unchanged AC.** AC-9.2 asserts byte-equality of `workflow_phase` AND `kanban_column`. The `updated_at` column may legitimately tick if any trigger fires. Implementation must avoid triggering touch of the parent row when only appending a phase_event.

## §8 Verification Mapping

| AC | Verification mechanism | Test file |
|---|---|---|
| AC-9.x | DB introspection + phase_events query + entity_display 1:1 check | `test_issue_spawn.py` (new) |
| AC-10.x | Multi-call orchestration + entity_relations query + idempotency replay + cross-closer | `test_complete_phase_closes.py` (new) |
| AC-MR.x | Migration runner + PRAGMA + sqlite_master string assert + dump-compare + FK enforcement | `test_migration_14_safety.py` (new) |
| AC-BM.x | ENTITY_MACHINES introspection + transition smoke tests | `test_entity_lifecycle.py` (extended) |
| AC-CL.x | grep lint + doctor check assertion + DB-state regression | `test_cleanup_suffix_parsers.py` (new) + `test_doctor.py` (extended) |
