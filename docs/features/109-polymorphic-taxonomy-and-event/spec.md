# Spec: Feature 109 — Polymorphic Taxonomy and Event-Sourced State

- **Project:** P003-entity-system-redesign
- **Feature:** 109-polymorphic-taxonomy-and-event
- **Phase:** Phase 2 of project roadmap
- **Mode:** full
- **Status:** Draft (revision 2 after spec-reviewer iteration 1)
- **Created:** 2026-05-12
- **Last updated:** 2026-05-12
- **PRD reference:** `docs/projects/P003-entity-system-redesign/prd.md` (brainstorm-equivalent source — project decomposition crystallized scope)
- **Roadmap reference:** `docs/projects/P003-entity-system-redesign/roadmap.md`
- **Fixes delivered (per PRD union):** F11 (6-type taxonomy with `kind` + `lifecycle_class`), F2 (`phase_events` as sole state-change primitive), F3 (atomic promotion via single UPDATE + event append; drop `enforce_immutable_entity_type` trigger), F12 (split `register_entity` raises-on-conflict from `upsert_entity` idempotent; audit 10 INSERT OR IGNORE call sites)
- **Constraint:** No backward compatibility on code paths. Append-only event log preservation is the one exception (legacy `phase_events` rows must remain valid post-CHECK-expansion; this is data preservation, not code-path compatibility).
- **Depends on:** Feature 108-workspace-identity-foundation (completed, v4.17.0)

---

## 1. Overview

Feature 109 transforms the entity model along four interlocking axes:

1. **Polymorphic taxonomy (F11)** — Replace the flat `entity_type` enum (currently 4 production values: `feature`, `backlog`, `brainstorm`, `project`; verified at live DB: `SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type` returns these four) with a three-column discriminator: `type` (4 values active in this feature), `kind` (per-type subtypes), `lifecycle_class` (state-machine selector). The flat enum confuses *shape* with *state machine*; the new scheme decouples them.

2. **Event-sourced state (F2)** — The `phase_events` table already exists (`database.py:1472-1489`) but is currently used only for analytics / backfill. Promote it to the canonical state-change primitive. `entities.status` and `workflow_phases.workflow_phase` become projections derived from event history — not direct write targets.

3. **Atomic promotion (F3)** — Backlog→feature promotion today requires a state transition + new `register_entity` call (separate row, separate uuid). Replace with a single-transaction `promote_entity(uuid, new_kind, new_lifecycle_class)` that performs one UPDATE + one `phase_events` append, preserving uuid identity. The `enforce_immutable_entity_type` trigger blocks this path today and must be dropped at every source-code definition site (6 total in `database.py`).

4. **Register / upsert split (F12)** — `register_entity` at `database.py:3343` silently swallows conflicts via `INSERT OR IGNORE` at `database.py:3451`. Production callers split between idempotent-intent and raise-on-conflict-intent; the silent-ignore default masks both kinds of bugs. Introduce `upsert_entity` as a separate explicit API for idempotent paths; `register_entity` raises `EntityExistsError`. Audit and route all 10 production INSERT OR IGNORE sites in `plugins/pd/hooks/lib/entity_registry/database.py`.

### Current state (verified 2026-05-12)

- **Already complete (feature 108):** `entities.workspace_uuid` exists with `UNIQUE(workspace_uuid, type_id)`; `entities.parent_type_id` column dropped (production DB confirms only `parent_uuid` present); `workspaces` table established.
- **In scope (feature 109):**
  - `entities` lacks `type`, `kind`, `lifecycle_class` columns — all routing keys off `entity_type` (flat string).
  - `phase_events` exists but is analytics-only; `entities.status` and `workflow_phases.workflow_phase` remain direct write targets.
  - `enforce_immutable_entity_type` trigger has **6 source-code definitions** in `database.py` (at lines 136, 254, 655, 1101, 1988, 2414) corresponding to different schema-creation paths (initial create, migration epochs, copy-rename recreations). Verification: `grep -n 'enforce_immutable_entity_type' plugins/pd/hooks/lib/entity_registry/database.py` returns 6 production matches.
  - `upsert_entity` does not exist anywhere in `plugins/pd/`.
  - **10 production `INSERT OR IGNORE` SQL statements** in `database.py`. Verification: `grep -n 'INSERT OR IGNORE INTO' plugins/pd/hooks/lib/entity_registry/database.py` returns 10 matches (lines 1587, 1603, 1630, 1657, 3241, 3302, 3451, 5058, 5176, 5525). Six additional grep matches at lines 1435, 3292, 3357, 4987, 5173, 5489 are docstring references — not production SQL — and are out of scope for the audit table but in scope for documentation cleanup.
  - `ENTITY_MACHINES` in `entity_lifecycle.py:18-56` only covers `brainstorm` and `backlog`; features/projects use a separate `WorkflowStateEngine` (`workflow_engine/entity_engine.py`). The two-engine split is structurally what F11's `lifecycle_class` discriminator collapses (collapse itself deferred to feature 110).
  - `FIVE_D_ENTITY_TYPES` frozenset at `entity_engine.py:35-37` (`{"initiative", "objective", "key_result", "project", "task"}`) — five types of which four (`initiative`, `objective`, `key_result`, `task`) have **0 production rows** (verified live DB). Call sites at `entity_engine.py:151` and `entity_engine.py:251`.
  - Live DB anomaly: 1 row in `workflow_phases` with `type_id = 'feature:'` (empty after colon) — must be cleaned up in migration.

---

## 2. Functional Requirements

Every FR below has measurable acceptance criteria and a verification command/query. All implementation references use the `plugins/pd/hooks/lib/entity_registry/` path unless otherwise noted.

### FR-1: 6-type Polymorphic Taxonomy Schema

Add three new columns to `entities`:

| Column | Type | Domain | Purpose |
|--------|------|--------|---------|
| `type` | TEXT NOT NULL | `{workspace, work, container, brainstorm}` (4 values populated in this feature) | Top-level polymorphic discriminator (storage shape) |
| `kind` | TEXT NOT NULL | per-type, see below | Subtype within `type` (semantic role) |
| `lifecycle_class` | TEXT NOT NULL | `{feature_flow, work_flow, container_flow, brainstorm_flow, none}` | State machine selector |

**Allowed `kind` values per `type`:**

- `type='work'` → `kind ∈ {feature, backlog}` (bug + task deferred until feature 111 creates rows of those kinds — adding them to the CHECK enum now would create forward-reference coupling that this revision removes)
- `type='container'` → `kind = project`
- `type='brainstorm'` → `kind = brainstorm`
- `type='workspace'` → `kind = workspace`

The `type` enum is reserved at 4 values in this feature. Future features (110, 111) extend the enum (`artifact` for feature 110 markdown projections; `phase_event` for event-log materialization if needed) via additive migrations — each future enum value ships in the feature that creates rows of that type. This avoids the forward-reference anti-pattern flagged in iteration 1.

**CHECK constraint:** Enforce both the `type` enum and the per-`type` `kind` enum at schema level via a single composite CHECK clause. Verification: attempting to insert `type='work', kind='project'` raises `sqlite3.IntegrityError: CHECK constraint failed: entities`.

**Backfill mapping (one-to-one from current `entity_type`):**

| Current `entity_type` | → `type` | → `kind` | → `lifecycle_class` |
|------------------------|----------|----------|---------------------|
| `feature` | `work` | `feature` | `feature_flow` |
| `backlog` | `work` | `backlog` | `work_flow` |
| `brainstorm` | `brainstorm` | `brainstorm` | `brainstorm_flow` |
| `project` | `container` | `project` | `container_flow` |
| `workspace` (post-108) | `workspace` | `workspace` | `none` |

**Acceptance Criteria:**

- **AC-1.1:** Schema migration adds `type`, `kind`, `lifecycle_class` columns to `entities` with NOT NULL constraints; rollback migration removes them. Verification: `PRAGMA table_info(entities)` lists all three columns with `notnull=1` post-migration.
- **AC-1.2:** Backfill populates every existing entity row per the mapping table above. Verification: capture `pre_count = SELECT COUNT(*) FROM entities` immediately before migration; post-migration, `SELECT COUNT(*) FROM entities WHERE type IS NULL OR kind IS NULL OR lifecycle_class IS NULL` returns 0 AND `SELECT COUNT(*) FROM entities` equals `pre_count` minus the orphan rows removed in AC-5.3 (target: removes the single `type_id='feature:'` row in `workflow_phases`; the `entities` row count is unaffected by AC-5.3, so the equation is `post_count == pre_count`).
- **AC-1.3:** Composite CHECK constraint rejects invalid `(type, kind)` pairs. Synthetic test inserts `(type='work', kind='project')` and asserts `IntegrityError` raised. Test also verifies the four valid pairs all insert successfully.
- **AC-1.4:** `entity_type` column is dropped from `entities` after backfill verification. All reader code paths previously consulting `entity_type` are rewritten to read `kind` or `type` as appropriate. **Audit boundary:** `grep -rn '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp_server/` returns 0 production references at completion. Explicitly permitted exceptions (allowed to retain `entity_type` references): (a) the migration script itself (renames `entity_type` to `kind` during backfill), (b) the `_migrate_*` historical migration functions in `database.py` that document past schema epochs, (c) test fixtures under `plugins/pd/tests/` that intentionally exercise pre-migration schema. All other matches must be eliminated.
- **AC-1.5:** `FIVE_D_ENTITY_TYPES` frozenset at `entity_engine.py:35-37` is removed; both call sites (`entity_engine.py:151`, `entity_engine.py:251`) re-keyed on `type='container'` membership. Verification: `grep -rn 'FIVE_D_ENTITY_TYPES' plugins/pd/` returns 0 production hits; the two call sites' new logic uses `entities.type` lookup.
- **AC-1.6:** `(workspace_uuid, type_id)` UNIQUE constraint preserved (composite key set in feature 108 remains intact); a new compound index `idx_entities_type_kind ON entities(type, kind)` is added to support polymorphic-query workloads.
- **AC-1.7:** **Migration immutability:** the backfill itself does NOT rewrite any `type_id` values — existing prefixes (e.g., `feature:042-foo`, `backlog:00367`) are byte-identical pre- and post-migration. Verification: `SELECT type_id FROM entities ORDER BY type_id` before and after migration produces byte-identical output (diff is empty).

> **Note on `type_id` mutability:** AC-1.7 applies to the *migration*. The runtime `promote_entity` function in FR-3 explicitly rewrites the `type_id` prefix on demand (see AC-3.3). The two are not in tension because migration backfill and runtime promotion are distinct operations on different rows at different times.

### FR-2: phase_events as Sole State-Change Primitive — Path A (Triggers)

This spec **commits to Path A: trigger-based projection**. Rationale: Path B (drop `entities.status`, reconstruct via view) requires rewriting every reader (≥20 call sites across hooks, MCP server, and skills) — a multi-feature undertaking that exceeds feature 109's scope. Path A is contained to the schema layer and the small set of writers, leaving readers untouched. Path B may be revisited in feature 110 or later.

**Schema changes to `phase_events`:**

- Expand the `event_type` CHECK constraint at `database.py:1485` (currently `('started','completed','skipped','backward')`) to include:
  - `entity_created` — appended automatically by `register_entity` / `upsert_entity` insert (and on the insert branch of upsert)
  - `entity_status_changed` — appended on any `entities.status` change
  - `entity_promoted` — emitted by `promote_entity` (see FR-3)
- Add nullable `metadata` column (TEXT, JSON) for event-specific payload (e.g., `{"old_status": "planned", "new_status": "active"}`).
- Empirical verification of JSON storage: `>>> import json; json.dumps({"old_status": "planned", "new_status": "active"}) → '{"old_status": "planned", "new_status": "active"}'`.
- Empirical verification of SQLite ALTER TABLE CHECK expansion limitation: `>>> import sqlite3; c=sqlite3.connect(':memory:'); c.execute("CREATE TABLE t(x TEXT CHECK(x IN ('a','b')))"); c.execute("ALTER TABLE t ALTER COLUMN x ...")` raises `sqlite3.OperationalError: near "ALTER": syntax error` — confirms SQLite does not support modifying CHECK in place. Migration uses the documented copy-rename pattern (https://www.sqlite.org/lang_altertable.html § 8).

**Projection mechanism (Path A specifics):**

- Direct `UPDATE entities SET status = ...` outside of the new `append_phase_event(...)` helper is forbidden. Enforcement: a new trigger `enforce_status_via_events` raises if `entities.status` is updated when `phase_events` has not been appended in the same transaction. (Implementation detail: SQLite triggers can inspect inserted rows via `sqlite_sequence` or use a transaction-local flag table — design phase locks the exact mechanism, but the WHAT is fixed here: direct UPDATE outside the helper raises.)
- All status writes route through a single new helper: `append_phase_event(type_id, event_type, *, metadata=None, project_id=None, iterations=None, reviewer_notes=None) → str` (returns event uuid). Inside one transaction it INSERTs the event row and UPDATEs the projection columns (`entities.status` for `entity_status_changed`/`entity_promoted`/`entity_created`; `workflow_phases.workflow_phase` for `started`/`completed`/`skipped`/`backward`).
- The `complete_phase` and `transition_phase` MCP entry points are refactored to call `append_phase_event(..., event_type='completed'|'started'|'skipped'|'backward')` instead of their current direct UPDATEs on `workflow_phases`.

**Acceptance Criteria:**

- **AC-2.1:** A trigger `enforce_status_via_events` (or equivalent enforcement mechanism — exact name selected in design) raises on any direct `UPDATE entities SET status = ?` issued outside the `append_phase_event` helper. Synthetic test: connect raw sqlite3, run `UPDATE entities SET status='active' WHERE uuid=?` without preceding phase_events INSERT, assert `IntegrityError` (or matching trigger-raised exception) raised.
- **AC-2.2:** Every entity state change has a corresponding `phase_events` row. Synthetic test: register an entity (1 `entity_created` event), transition through `planned → active → completed` via `append_phase_event` (2 `entity_status_changed` events). Assert `SELECT event_type FROM phase_events WHERE type_id = ? ORDER BY timestamp` returns exactly `['entity_created', 'entity_status_changed', 'entity_status_changed']` AND `entities.status` reads `'completed'`.
- **AC-2.3:** Projection consistency: at any point in time, `entities.status` equals the `metadata.new_status` of the most-recent `entity_status_changed` event for that uuid (or the initial status from the most-recent `entity_created` event if no status changes exist). Synthetic test: insert events through `append_phase_event`, assert the projected status matches the latest event's stated state.
- **AC-2.4:** `phase_events.event_type` CHECK constraint accepts all 7 values: the 4 legacy values (`started`, `completed`, `skipped`, `backward`) AND the 3 new values (`entity_created`, `entity_status_changed`, `entity_promoted`). Verification: after migration, run 7 dry-run inserts (one per value) — all succeed. An 8th insert with an invalid value (e.g., `'invalid'`) raises `IntegrityError`. **Reason for accepting legacy values:** the `phase_events` event log is append-only data (not a code path); existing rows must remain queryable. This is data preservation, not the "no backward compatibility" code-path rule which still applies to all writer code.
- **AC-2.5:** Migration adds the new event types via copy-rename pattern (per the empirical verification above); rollback narrows the CHECK back. Migration acquires the existing WAL-mode write lock pattern (see `CLAUDE.md` "SQLite lock recovery") and does not silently swallow `OperationalError`. Rollback is exercised in a test using a copy of the live DB schema.
- **AC-2.6:** No production caller writes directly to `workflow_phases.workflow_phase`. Verification: `grep -rn 'UPDATE workflow_phases' plugins/pd/hooks/lib/ plugins/pd/mcp_server/` returns 0 production matches (allowed exceptions: the `append_phase_event` helper itself, and historical `_migrate_*` functions). All `complete_phase` and `transition_phase` MCP call sites route through `append_phase_event`.
- **AC-2.7:** `entities.updated_at` remains correct under the new model — `append_phase_event` updates it to `MAX(timestamp)` in the same transaction. Synthetic test asserts `entities.updated_at == max(phase_events.timestamp WHERE type_id=?)` post-update.
- **AC-2.8:** The new `append_phase_event` helper appends exactly one row per call AND updates the relevant projection columns atomically. Synthetic test: monkey-patch the UPDATE step to raise after the event INSERT; assert transaction rolls back, no event row visible post-rollback, projection unchanged.

### FR-3: Atomic Promotion

Replace the current backlog→feature promotion path with `promote_entity(uuid, new_kind, new_lifecycle_class) → dict`. The function performs:

1. Pre-flight: read existing row by `uuid`. If `entities.type_id` prefix change would collide with an existing `(workspace_uuid, new_type_id)` row, raise `PromotionConflictError`. (Example: promoting `backlog:42` → `feature:42` while a row with `type_id='feature:42'` already exists in the same workspace.)
2. Single `UPDATE entities SET kind = ?, lifecycle_class = ?, type_id = ?, updated_at = ? WHERE uuid = ?` in one transaction. (The new `type_id` has the form `{new_kind}:{entity_id}` where `entity_id` is parsed from the existing `type_id` after the colon — preserving the numeric/slug suffix.)
3. Append `phase_events` row via `append_phase_event(..., event_type='entity_promoted', metadata={"old_kind":..., "new_kind":..., "old_lifecycle_class":..., "new_lifecycle_class":..., "old_type_id":..., "new_type_id":...})`.
4. Return the updated entity dict.

**Trigger drop (6-site sweep):** Remove `enforce_immutable_entity_type` at all 6 source-code definitions (lines 136, 254, 655, 1101, 1988, 2414 in `database.py`). Each site corresponds to a different schema-creation epoch (initial create, migrations, copy-rename recreations from prior features). The new migration also issues `DROP TRIGGER IF EXISTS enforce_immutable_entity_type` to remove the runtime trigger.

**Allowed promotion transitions:** `promote_entity` accepts any `(new_kind, new_lifecycle_class)` pair that satisfies the FR-1 composite CHECK constraint. No kind-to-kind transitions are otherwise restricted at this layer. If callers need to enforce business-logic restrictions (e.g., "only backlog → feature is meaningful"), they wrap `promote_entity` with their own validation; the DB-layer function is permissive within the schema.

**Acceptance Criteria:**

- **AC-3.1:** **Source-code sweep:** `grep -n 'enforce_immutable_entity_type' plugins/pd/hooks/lib/entity_registry/database.py` returns 0 production matches at completion (the migration's `DROP TRIGGER` statement is permitted). Explicit list: all 6 `CREATE TRIGGER ... enforce_immutable_entity_type` definitions at lines 136, 254, 655, 1101, 1988, 2414 are removed or guarded so no schema-recreation path re-introduces them. **Runtime sweep:** `SELECT name FROM sqlite_master WHERE type='trigger' AND name='enforce_immutable_entity_type'` returns 0 rows post-migration on the live DB.
- **AC-3.2:** `promote_entity` exists as a public method on the DB class. Signature: `promote_entity(self, uuid: str, new_kind: str, new_lifecycle_class: str, *, project_id: str | None = None) -> dict`. Returns the updated entity row as a dict.
- **AC-3.3:** Synthetic promotion test: create backlog entity, capture `uuid`; call `promote_entity(uuid, 'feature', 'feature_flow')`; assert (a) `uuid` unchanged, (b) `kind='feature'`, (c) `lifecycle_class='feature_flow'`, (d) `type_id` rewritten from `backlog:{n}` to `feature:{n}` (entity_id suffix preserved byte-identical), (e) `phase_events` has one row with `event_type='entity_promoted'` and metadata containing both `old_*` and `new_*` fields, (f) `parent_uuid` and `workspace_uuid` unchanged.
- **AC-3.4:** Promotion preserves FK targets — any `entity_dependencies` rows referencing the promoted uuid (as `from_uuid` or `to_uuid`) remain valid because `uuid` is unchanged. Synthetic test: create backlog with dependency on a feature, promote the backlog to feature, query dependencies; assert dependency count unchanged and both endpoints still resolvable.
- **AC-3.5:** Promotion is atomic — if any of (UPDATE, phase_events INSERT) fail, the transaction rolls back and no partial state is visible. Synthetic test: monkey-patch the event-append step to raise; assert pre-promotion `kind`, `lifecycle_class`, and `type_id` are intact and no orphan event row exists.
- **AC-3.6:** Promotion is UNIQUE-safe: pre-create `feature:42` in workspace W; create `backlog:42` in the same workspace W; attempt `promote_entity(backlog_uuid, 'feature', 'feature_flow')`; assert `PromotionConflictError` raised (typed exception, subclass of `Exception` or named base); assert both rows untouched post-failure (original `backlog:42` still has `kind='backlog'`).
- **AC-3.7:** **Free-text reference verification (note, not an enforceable AC):** existing `(promoted → feature:X)` strings in retro docs remain literally accurate because the post-promotion `type_id` matches the format `feature:X`. This is an observable consequence of AC-3.3.(d), not a separately testable property. A grep at completion lists the docs that contain such strings as informational; no CI gate.

### FR-4: register_entity / upsert_entity Split

Introduce a hard separation between raise-on-conflict and idempotent insert semantics. Audit and re-route all 10 production `INSERT OR IGNORE` SQL statements in `database.py`.

**New API surface:**

- `register_entity(...)` — RAISES `EntityExistsError` (new exception class in `plugins/pd/hooks/lib/entity_registry/exceptions.py`) on `(workspace_uuid, type_id)` conflict. No silent ignore.
- `upsert_entity(...)` — Idempotent. Same signature as `register_entity`. On conflict, performs `UPDATE ... SET name = ?, status = ?, parent_uuid = ?, metadata = ?, updated_at = ? WHERE workspace_uuid = ? AND type_id = ?` and returns the existing uuid. No new uuid is generated when upserting an existing row.
- On the **insert branch** (no conflict), `upsert_entity` emits exactly one `entity_created` phase_event via `append_phase_event`, identical to `register_entity`'s emission. Event-stream parity is required regardless of which API was used.
- On the **conflict branch** (existing row), `upsert_entity` emits at most one `entity_status_changed` phase_event — and only if `status` changed. If `name`, `parent_uuid`, or `metadata` changed without a `status` change, the UPDATE runs but no event is emitted (status is the event-tracked column; non-status mutations are silent edits).

**INSERT OR IGNORE audit (10 production SQL sites in `database.py`):**

Each row below identifies the caller, what condition the original code expected, and the chosen route with rationale.

| Line | Table | Calling function | Original intent | Route | Rationale |
|------|-------|------------------|-----------------|-------|-----------|
| 1587 | phase_events | `_backfill_phase_events_from_workflow_phases` (or similar; verify name at implement time) | Idempotent replay of historical events | upsert (via direct INSERT — phase_events has its own dedup index, not the entity upsert API) | Backfill is replayed on every migration boot; events have a partial-UNIQUE backfill-dedup index (`database.py:1517-1518`). Existing dedup mechanism is correct; this site retains its current semantics but the comment is updated to say "Idempotent via `phase_events_backfill_dedup` partial-UNIQUE index". No call to `upsert_entity` because the target table is `phase_events`, not `entities`. |
| 1603 | phase_events | same backfill helper | Idempotent replay | upsert (in-table) | Same as 1587. |
| 1630 | phase_events | same backfill helper | Idempotent replay | upsert (in-table) | Same as 1587. |
| 1657 | phase_events | same backfill helper | Idempotent replay | upsert (in-table) | Same as 1587. |
| 3241 | entity_tags | `add_entity_tag` (verify at implement) | Tag attach is naturally idempotent; "tag entity X with Y" should not raise if already tagged | upsert (in-table; this is `entity_tags`, not `entities`) | Tag attach is a many-to-many idempotent attach. Retains INSERT OR IGNORE semantics in the entity_tags table; the rationale is documented inline. Not an `upsert_entity` call. |
| 3302 | entity_okr_alignment | `add_okr_alignment` (verify at implement) | OKR attach is idempotent | upsert (in-table) | Same pattern as entity_tags. |
| 3451 | entities | `register_entity` | **AMBIGUOUS in current code:** docstring says "INSERT OR IGNORE semantics" but no caller is documented as either intent-preserving or intent-raising | **register (raise)** | This is the canonical register site. After F12, `register_entity` removes its `INSERT OR IGNORE` and raises `EntityExistsError` on conflict. Idempotent callers must migrate to `upsert_entity` (FR-4 callsite audit identifies them — see below). |
| 5058 | workflow_phases | `init_entity_workflow` (or similar; verify) | "Initialize workflow row for entity if not already present" — idempotent by design | upsert (in-table) | This is a row-init for a different table. Retains INSERT OR IGNORE on workflow_phases. Not an `upsert_entity` call. |
| 5176 | entity_dependencies | `add_dependency` | "Add dependency edge if not already present" — idempotent | upsert (in-table) | Dependency add is a many-to-many idempotent attach. Retains INSERT OR IGNORE on entity_dependencies. |
| 5525 | entities | `register_entities_batch` (bulk backfill) | Bulk backfill is intentionally idempotent — re-running the migration script must not raise | **upsert_entity (new API)** | This is the bulk-load path. Migration retries / re-runs require idempotency. Re-route from raw `INSERT OR IGNORE INTO entities` to the new `upsert_entity` API to preserve event-stream parity (each backfill row emits one `entity_created` event per AC-2.2). |

**Per-call-site routing summary:**

- 1 site (line 3451) becomes `register_entity` raising on conflict.
- 1 site (line 5525) re-routes to the new `upsert_entity` API and emits events.
- 8 sites remain INSERT OR IGNORE on non-`entities` tables (`phase_events`, `entity_tags`, `entity_okr_alignment`, `workflow_phases`, `entity_dependencies`). These tables have their own idempotency contracts (partial-UNIQUE indexes, composite primary keys) that operate independently of the `entities`-row identity API. The audit acknowledges these and documents the per-table rationale inline.

**Acceptance Criteria:**

- **AC-4.1:** `EntityExistsError` exists as a named exception class in `plugins/pd/hooks/lib/entity_registry/exceptions.py` (or chosen module; design phase locks the file). Test: import succeeds; `issubclass(EntityExistsError, Exception)` is True; exception carries `workspace_uuid` and `type_id` attributes for caller inspection.
- **AC-4.2:** `register_entity` raises `EntityExistsError` on `(workspace_uuid, type_id)` conflict. Synthetic test: register entity A; second `register_entity` call with same `(workspace_uuid, type_id)` raises; first row untouched (no UPDATE, no second uuid generated, no `entity_status_changed` event emitted).
- **AC-4.3:** `upsert_entity` exists as a public DB method. Signature mirrors `register_entity` (workspace_uuid, type_id, name, status, parent_uuid, metadata). Returns the entity uuid in both insert and update cases.
- **AC-4.4:** `upsert_entity` event semantics:
  - On insert branch (no conflict): emits exactly one `entity_created` phase_event identical in shape to `register_entity`'s emission.
  - On conflict branch with status change: emits exactly one `entity_status_changed` phase_event with `metadata={"old_status": ..., "new_status": ...}`.
  - On conflict branch without status change (only `name` / `parent_uuid` / `metadata` differ): UPDATE runs, no phase_event emitted.
  - On conflict branch with no field differences: no UPDATE issued, no phase_event emitted.
  - Synthetic test covers all four branches.
- **AC-4.5:** All 10 production `INSERT OR IGNORE INTO` SQL statements in `database.py` are catalogued in the audit table above, each with its routing decision documented in the code at the call site. Verification: `grep -n 'INSERT OR IGNORE INTO entities' plugins/pd/hooks/lib/entity_registry/database.py` returns 0 production hits (sites 3451 and 5525 both eliminated — 3451 via register-raise, 5525 via upsert_entity). The 8 sites on non-`entities` tables retain their INSERT OR IGNORE with updated inline comments justifying the in-table idempotency.
- **AC-4.6:** Every routed site has a unit test asserting the chosen semantics:
  - Site 3451 (register_entity): test asserts conflict raises `EntityExistsError`.
  - Site 5525 (register_entities_batch via upsert): test asserts idempotent re-run produces same row count and exactly N `entity_created` events on first run, 0 additional on second run.
  - Sites 1587/1603/1630/1657 (phase_events backfill): test asserts replay produces no duplicate event rows.
  - Site 3241 (entity_tags): test asserts duplicate tag attach is a no-op.
  - Site 3302 (entity_okr_alignment): test asserts duplicate alignment attach is a no-op.
  - Site 5058 (workflow_phases init): test asserts duplicate init is a no-op.
  - Site 5176 (entity_dependencies): test asserts duplicate edge add is a no-op.
- **AC-4.7:** No production caller catches a generic `sqlite3.IntegrityError` from the `entities` insert path expecting silent ignore. Audit: `grep -rn 'sqlite3.IntegrityError\|except IntegrityError' plugins/pd/` lists any catch sites; each is reviewed and either (a) explicitly catches `EntityExistsError` for the register path, or (b) migrated to `upsert_entity` for idempotent paths, or (c) documented as catching a different table's IntegrityError unrelated to entities.

### FR-5: Migration Safety and Idempotency

Schema changes ship as a single migration with `up` and `down` paths.

**Acceptance Criteria:**

- **AC-5.1:** Migration is reversible. `down` path: removes `type`, `kind`, `lifecycle_class` columns; restores `entity_type` from `kind` (mapping is one-to-one and lossless within the backfill set); re-adds `enforce_immutable_entity_type` trigger at one canonical schema location (not all 6 historical sites — those were epoch artifacts and the down-migration only needs to restore the runtime trigger); narrows the `phase_events.event_type` CHECK back to the 4 legacy values; removes `upsert_entity` and reverts `register_entity` to its INSERT OR IGNORE form. Down-migration is exercised on a copy of the live DB in a test.
- **AC-5.2:** Migration is idempotent — running twice produces no error and no schema drift. Verification: capture `.schema` after first run, run again, capture `.schema` again, diff is empty.
- **AC-5.3:** Pre-migration cleanup removes the malformed `workflow_phases` row with `type_id = 'feature:'` (verified present in live DB, 2026-05-12). Migration logs this cleanup separately so it's auditable: a one-line `INFO` log emitted to stderr before the cleanup DELETE.
- **AC-5.4:** Migration acquires the existing WAL-mode write lock pattern (see `CLAUDE.md` "SQLite lock recovery") and does not silently swallow `OperationalError`. If a stale process holds the lock, the migration fails loudly with the existing helpful error message ("kill stale Python/MCP processes...").
- **AC-5.5:** Bash 3.2 / macOS BSD portability preserved across any new shell hooks added for this feature (none expected, but listed for explicitness per project cross-cutting concerns).

---

## 3. Non-Functional Requirements

### NFR-1: Performance

- Polymorphic-query workloads (`SELECT ... WHERE type = 'work' AND kind = 'feature'`) must use the new `idx_entities_type_kind` index. Verification: `EXPLAIN QUERY PLAN SELECT * FROM entities WHERE type = 'work' AND kind = 'feature'` shows `USING INDEX idx_entities_type_kind` (not `SCAN entities`).
- `phase_events` writes add at most one INSERT per state change. The append-only access pattern aligns with SQLite's strengths and WAL mode; no additional locking concerns expected.
- **Migration runtime gate (behavioral, not wall-clock):** the migration completes without exceeding SQLite's default `busy_timeout` (typically 5000 ms; verified at `>>> import sqlite3; c=sqlite3.connect(':memory:'); c.execute('PRAGMA busy_timeout').fetchone() → (5000,)` — actual project default may differ but is captured by the test) and runs the full transaction without intermediate yields. Verification: test on a synthetic DB containing the same row counts as the live DB (~700 rows across entities + workflow_phases + phase_events), with the test asserting the migration completes within the configured busy_timeout. The previous wall-clock target ("<5s on MacBook M1/M2") is removed as non-gateable per spec-reviewer iteration 1 feedback.

### NFR-2: Observability

- Every promotion, status change, and entity creation emits a `phase_events` row with sufficient metadata to reconstruct *who* changed *what* *when*. `metadata.actor` field is OPTIONAL in this feature (no actor identity surface yet); kept as None placeholder.
- The doctor health check (existing `~/.claude/pd/doctor.sh` or equivalent) gains a new check: "Any production `INSERT OR IGNORE INTO entities` statements in `plugins/pd/hooks/lib/entity_registry/database.py`?" — fails the doctor run if grep finds one. (Note: this check is narrower than "any INSERT OR IGNORE anywhere" because in-table idempotency on other tables remains a valid pattern.)

### NFR-3: Atomic commit discipline

- Per memory entry "Atomic commit discipline in schema migrations": each commit in this feature's implementation MUST be independently reversible. The implementation order is enforced as sequential commits, each gated by passing tests:
  1. Add `type`, `kind`, `lifecycle_class` columns with NOT NULL DEFAULT (initial backfill values).
  2. Backfill columns via UPDATE (tests verify mapping correctness).
  3. Add CHECK constraint (via copy-rename if needed).
  4. Add `idx_entities_type_kind` index.
  5. Update all readers of `entity_type` to read `kind`/`type`.
  6. Drop `entity_type` column.
  7. Expand `phase_events.event_type` CHECK (copy-rename).
  8. Add `entity_created`, `entity_status_changed`, `entity_promoted` event emission paths via `append_phase_event` helper.
  9. Add `enforce_status_via_events` trigger (or equivalent enforcement).
  10. Drop `enforce_immutable_entity_type` trigger (runtime DROP) and remove all 6 source-code definitions.
  11. Add `promote_entity` function and `PromotionConflictError`.
  12. Split `register_entity` (raise) from new `upsert_entity` (idempotent).
  13. Re-route line-3451 and line-5525 sites per the audit table.
  14. Add doctor check.
- Each commit ships with the tests for its scope. Bisect-bug locality is preserved.

---

## 4. Acceptance Criteria Roll-Up

A feature is considered complete when:

- [ ] All AC-1.x through AC-5.x pass in CI.
- [ ] Live DB on a developer machine successfully migrates and the post-migration `entities` table query returns the same row count as pre-migration.
- [ ] `pytest plugins/pd/tests/` passes with at least one new test file per FR (`test_polymorphic_taxonomy.py`, `test_event_sourced_state.py`, `test_atomic_promotion.py`, `test_register_upsert_split.py`, `test_migration_safety.py`).
- [ ] `grep -n 'INSERT OR IGNORE INTO entities' plugins/pd/hooks/lib/entity_registry/database.py` returns 0 (production code).
- [ ] `grep -n 'enforce_immutable_entity_type' plugins/pd/hooks/lib/entity_registry/database.py` returns 0 (trigger source removed; DROP statement in migration is permitted).
- [ ] `grep -rn 'FIVE_D_ENTITY_TYPES' plugins/pd/hooks/lib/` returns 0 (frozenset removed; callers re-keyed).
- [ ] `grep -rn '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp_server/` returns 0 production references (column dropped; reads route through `kind` / `type`; permitted exceptions per AC-1.4).
- [ ] At least one synthetic test per FR demonstrates the bad-state-rejection path (e.g., invalid `(type, kind)` pair → IntegrityError) AND the projection-determinism path (e.g., rebuild from events == direct read).

---

## 5. Scope

### In Scope

- Schema additions: `entities.type`, `entities.kind`, `entities.lifecycle_class`, `idx_entities_type_kind`.
- Schema deletions: `entities.entity_type` column, `enforce_immutable_entity_type` trigger (at runtime AND all 6 source-code definitions).
- Schema modifications: `phase_events.event_type` CHECK expansion (4 → 7 values).
- API additions: `EntityExistsError`, `PromotionConflictError`, `upsert_entity`, `promote_entity`, `append_phase_event`.
- API modifications: `register_entity` (now raises), `complete_phase` / `transition_phase` MCP entry points (route through `append_phase_event`).
- Migration script with up/down paths and verification queries.
- Test files: one per FR plus migration tests.
- Doctor health check addition.

### Out of Scope

- **`type` enum values `artifact` and `phase_event`** — deferred to features 110 and 111 respectively. Each future feature adds the enum value via an additive migration alongside the first rows of that type.
- **Markdown projections / `pd-state.diff.md` generator** — feature 110 (Phase 3, M3 milestone).
- **`entity_display` table for renames** — feature 110.
- **Generalized data-file guard hook** — feature 110.
- **`issue_spawn` MCP and atomic closure linkage** — feature 111 (Phase 4, M4 milestone).
- **`kind` values `bug` and `task` under `type='work'`** — deferred to feature 111 (first rows of these kinds are created by `issue_spawn`).
- **Collapsing `ENTITY_MACHINES` and `WorkflowStateEngine` into a single `lifecycle_class`-keyed router** — the columns enable this collapse but the actual collapse is deferred to feature 110 to avoid scope creep.
- **Path B (event-only projection, drop `entities.status` column)** — explicitly rejected for this feature per FR-2 Path A commitment. May be revisited later.
- **Cross-workspace queries** — deliberately gated per project PRD; can be added later.
- **UUIDv7 substitution at register sites (F6)** — deferred per feature 108 spec to backlog (gated on Python 3.14+); feature 109 does not revisit.
- **Doctor `entity_type` reference check** — the narrower INSERT OR IGNORE check is in scope (NFR-2); a broader `entity_type` reference check would need to whitelist the migration script and is left for a follow-up.

---

## 6. Feasibility Assessment

### Assessment Approach

1. **First Principles:** SQLite supports ALTER TABLE ADD COLUMN, triggers, CHECK constraints, and partial indexes. Event sourcing in SQLite is a well-documented pattern. The 6-type taxonomy mapping from 4 production types is one-to-one and bounded — no data ambiguity.
2. **Codebase Evidence:**
   - `phase_events` table already exists (`database.py:1472-1489`) with append-only semantics and a partial-UNIQUE backfill-dedup index. Reuse, not new build.
   - Migration tooling already in place (`_migrate_to_uuid_pk` and similar in `database.py`). Pattern is reusable.
   - `register_entity` is a single function with a single `INSERT OR IGNORE` line (`database.py:3451`). The split is mechanically simple.
   - `WorkflowStateEngine` and `ENTITY_MACHINES` (`entity_lifecycle.py:18-56`) are the two state-machine surfaces; the `lifecycle_class` discriminator unifies the routing key but does not require collapsing the implementations into one (feature 110 may do that).
3. **External Evidence:**
   - SQLite ALTER TABLE limitations documented at https://www.sqlite.org/lang_altertable.html — CHECK constraint expansion requires the copy-rename pattern. Confirmed.
   - Event sourcing as projection pattern documented at https://martinfowler.com/eaaDev/EventSourcing.html — well-understood architectural pattern.

### Assessment

- **Overall:** Confirmed
- **Reasoning:** All four sub-fixes (F11, F2, F3, F12) use existing SQLite primitives, build on completed feature 108 infrastructure, and have one-to-one backfill mappings. The most complex operation is the CHECK constraint expansion (requires copy-rename), and that pattern is already used elsewhere in `database.py` migrations.
- **Key Assumptions:**
  - `phase_events.event_type` CHECK can be expanded via copy-rename without data loss — Verified at SQLite docs (https://www.sqlite.org/lang_altertable.html).
  - No production caller depends on the `enforce_immutable_entity_type` trigger raising — Verified by `grep -rn 'enforce_immutable_entity_type\|immutable entity_type' plugins/pd/` returning only the 6 schema-creation sites and tests; no application code expects the trigger to raise as a feature.
  - The trigger's 6 source-code definitions can all be safely removed because they were epoch artifacts from prior copy-rename migrations — Verified by reading the surrounding context at each of lines 136, 254, 655, 1101, 1988, 2414 (all inside `_migrate_*` functions or initial schema creation; none in runtime hot paths).
  - No caller of `register_entity` currently catches `sqlite3.IntegrityError` expecting silent ignore — Needs verification via AC-4.7 audit at implement time.
- **Open Risks:**
  - The `phase_events.event_type` CHECK expansion via copy-rename will require WAL-mode lock acquisition; if another pd process holds the lock, the migration fails. Mitigation: pre-migration check for stale processes per `CLAUDE.md` SQLite lock recovery guidance, surfaced through AC-5.4.
  - If readers in `entity_engine.py:151` and `entity_engine.py:251` are not the only `FIVE_D_ENTITY_TYPES` consumers, the migration may break a caller. Mitigation: audit pass via `grep -rn FIVE_D_ENTITY_TYPES plugins/pd/` at implement time captured by AC-1.5.
  - The `enforce_status_via_events` trigger (or equivalent enforcement) in AC-2.1 has a non-trivial implementation — design phase must lock the mechanism and verify it does not block migration backfill UPDATEs (which set status during the initial backfill before the trigger exists).

---

## 7. Dependencies

- **Feature 108-workspace-identity-foundation (completed, v4.17.0):** Provides `workspaces` table, `workspace_uuid` column, and `(workspace_uuid, type_id)` UNIQUE constraint. Feature 109 builds on this directly.
- **External:** Python 3.12+ (existing project floor); SQLite 3.x (existing); `pytest` (existing). No new dependencies added.

---

## 8. Open Questions (deferred to design phase — HOW, not WHAT)

These are HOW questions; the WHAT contracts above are stable.

1. **Exact mechanism for `enforce_status_via_events`:** A pure-SQLite trigger that inspects a transaction-local flag table vs a Python-side enforcement layer in the DB class. AC-2.1's contract is "direct UPDATE raises"; design phase locks the mechanism.
2. **JSON1 vs TEXT for `phase_events.metadata`:** Both are SQLite-native. Affects query ergonomics in future analytics but does not change the column contract for this feature.
3. **Doctor check placement:** Inside the existing `~/.claude/pd/doctor.sh` script vs a new dedicated Python check. Either satisfies NFR-2.
4. **`entity_type` column drop timing within the migration:** Single migration (current spec) vs split across two migration steps for safer rollback. Spec specifies single migration; design may split if rollback complexity warrants. This is a HOW question — the AC contracts (column gone at end-of-feature) are unaffected.

---

## 9. Test Plan Highlights

The taskify phase will expand these; spec lists the must-have test surfaces:

- `test_polymorphic_taxonomy.py` — schema add, backfill, CHECK constraint rejection, index existence, `FIVE_D_ENTITY_TYPES` removal verification, `entity_type` reader audit.
- `test_event_sourced_state.py` — every state change emits event; projection consistency; expanded `event_type` CHECK accepts new values; direct UPDATE outside helper raises; `append_phase_event` is atomic.
- `test_atomic_promotion.py` — promotion preserves uuid; trigger drop at all 6 sites; transaction rollback under partial failure; FK preservation; type_id prefix update; PromotionConflictError on UNIQUE collision.
- `test_register_upsert_split.py` — `EntityExistsError` raised on conflict; `upsert_entity` four-branch event semantics; one test per audited call site; `INSERT OR IGNORE INTO entities` grep returns 0.
- `test_migration_safety.py` — up/down reversible; idempotent; orphan cleanup; WAL lock acquisition.

---

## 10. Glossary

- **`type`** — Top-level polymorphic discriminator. 4 values active in feature 109: `workspace`, `work`, `container`, `brainstorm`. Two additional values (`artifact`, `phase_event`) are reserved at the conceptual level but added to the CHECK enum only when their respective features (110, 111) create rows of those types.
- **`kind`** — Per-`type` subtype. E.g., `(type='work', kind='feature')`. Semantic role within the shape.
- **`lifecycle_class`** — State machine selector. 5 values including `none`. Decoupled from `kind` so the same `kind` can adopt different state machines under future expansion.
- **`type_id`** — Existing colon-separated `{kind}:{entity_id}` string. Preserved byte-identical across this migration (AC-1.7); runtime `promote_entity` calls may rewrite the prefix on demand (AC-3.3).
- **Projection (event-sourcing sense)** — A read-optimized representation derived from the immutable event log. In this feature, `entities.status` is a projection of `phase_events` (Path A: trigger-maintained).

---

## Review History

### Spec-Reviewer Iteration 1 (2026-05-12)

**Reviewer:** pd:spec-reviewer (skeptic) — Anthropic Task fallback (codex CLI unavailable)
**Decision:** Needs Revision (4 blockers, 11 warnings + suggestions)

**Blockers addressed:**
- [blocker] INSERT OR IGNORE count inconsistent (claimed 14, actual 10 in production SQL). **Fix:** Restated count as 10 everywhere; documented the 6 docstring references as separate from the audit table; added explicit `grep -n 'INSERT OR IGNORE INTO'` command output expectation. (See §1, FR-4, AC-4.5)
- [blocker] `enforce_immutable_entity_type` trigger has 6 source-code definitions, not 1. **Fix:** Enumerated all 6 lines (136, 254, 655, 1101, 1988, 2414) in §1, FR-3, AC-3.1; added "source-code sweep" AC requiring grep returns 0 production matches.
- [blocker] FR-2 Path A vs Path B unresolved while ACs depend on choice. **Fix:** FR-2 explicitly commits to Path A (trigger-based projection) with rationale; Path B rejected for this feature (in §5 Out of Scope); all FR-2 ACs rewritten to Path A.
- [blocker] `artifact` and `phase_event` enum values added without in-feature rows. **Fix:** Removed both values from FR-1 CHECK enum; reserved them conceptually but they ship with features 110 and 111 via additive migrations; documented in §5 Out of Scope and §10 Glossary.

**Warnings addressed:**
- [warning] AC-1.2 hardcoded "457 entities" → restated as pre-migration count capture + post-migration equality assertion; literal numbers moved to informational §1.
- [warning] AC-4.4 upsert insert-event semantics unspecified → explicitly defined all 4 branches (insert/conflict×status-change/no-change).
- [warning] AC-1.4 "≥7 sites" ambiguous → replaced with explicit grep command + scope boundary + permitted exceptions.
- [warning] AC-3.6 free-text retro AC non-actionable → downgraded to "informational note", not an enforceable AC; renamed AC-3.6 → AC-3.7 with note framing.
- [warning] AC-3.3.(d) UNIQUE collision risk during promotion → added AC-3.6 (new) with `PromotionConflictError` pre-flight check; FR-3 step 1 documents the pre-flight.
- [warning] AC-1.7 vs AC-3.3 contradiction → added inline note clarifying migration-immutability vs runtime-promotion distinction.
- [warning] NFR-1 "<5s on MacBook" non-gateable → replaced with busy_timeout-based behavioral gate.
- [warning] AC-2.5 prose pretending to be REPL → replaced with real REPL transcript showing `sqlite3.OperationalError`.
- [warning] FR-4 9 sites all routed to upsert without per-call-site analysis → expanded audit table with calling function, original intent, and per-site rationale for every line.
- [warning] AC-2.4 "backward compatibility" phrasing → clarified as data preservation (append-only log), not code-path compatibility.
- [suggestion] state transition truth table for `promote_entity` → added "Allowed promotion transitions" prose under FR-3 (permissive at DB layer, business logic in callers).
