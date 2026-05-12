# Design: Feature 109 — Polymorphic Taxonomy and Event-Sourced State

- **Project:** P003-entity-system-redesign
- **Feature:** 109-polymorphic-taxonomy-and-event
- **Phase:** Phase 2 of project roadmap
- **Mode:** full
- **Status:** Draft (revision 2 after design-reviewer iteration 1)
- **Created:** 2026-05-12
- **Last updated:** 2026-05-12
- **Spec reference:** `docs/features/109-polymorphic-taxonomy-and-event/spec.md`
- **PRD reference:** `docs/projects/P003-entity-system-redesign/prd.md`
- **Migration version:** **12** (current schema_version = 11 at `database.py:2630`, last migration is `_migration_11_workspace_identity` from feature 108)
- **Depends on:** Feature 108-workspace-identity-foundation (completed, v4.17.0)

---

## 1. Architecture Overview

Feature 109 ships as a single new migration function `_migration_12_polymorphic_taxonomy_and_events` plus matching API additions on `EntityDatabase`. The migration follows the established 11-migration pattern (`database.py:2620 MIGRATIONS` dict) and the established transaction discipline (`PRAGMA foreign_keys OFF` outside `try`, `BEGIN IMMEDIATE` inside try, `foreign_key_check` pre and post, `schema_version` stamped inside the transaction).

The change is structured in five concurrent dimensions:

```
┌─────────────────────────────────────────────────────────────┐
│                    Migration 12                              │
│  (single _migration_12_polymorphic_taxonomy_and_events fn)   │
└─────────────┬───────────────────────────────────────────────┘
              │
   ┌──────────┼──────────┬──────────────┬─────────────────────┐
   │          │          │              │                     │
   ▼          ▼          ▼              ▼                     ▼
┌──────┐  ┌───────┐  ┌────────┐   ┌─────────┐         ┌────────────┐
│  F11 │  │   F2  │  │   F3   │   │   F12   │         │ Schema-wide│
│ Taxon│  │ Event │  │Promote │   │Reg/Upsrt│         │  cleanup   │
│ omy  │  │Source │  │ Trigger│   │  Split  │         │  (AC-5.3)  │
└──┬───┘  └───┬───┘  └────┬───┘   └────┬────┘         └────────────┘
   │          │           │            │
   │          │           │            │
   ▼          ▼           ▼            ▼
type/kind/  phase_events  drop 12     EntityExistsError
lifecycle_  +metadata col triggers    PromotionConflictError
class cols  +CHECK 4→7   (2×6 sites)  upsert_entity
+FTS5       +phase null- entity_id    promote_entity
rebuild     able + append split        register no longer
            _phase_event  + uniq-safe  ignores

```

The migration is **non-reversible** beyond a one-shot rollback (per spec AC-5.1). After rollback, only one canonical trigger definition is restored (not all 6 historical sites). This matches the precedent set by `_migration_11_workspace_identity_down` (the only currently-reversible migration; `database.py:2637 MIGRATIONS_DOWN`).

### Component Map

The implementation introduces / modifies these surfaces:

| Component | Where | Type | Purpose |
|-----------|-------|------|---------|
| `_migration_12_polymorphic_taxonomy_and_events` | `database.py` (new fn, registered at `MIGRATIONS[12]`) | new | The migration |
| `_migration_12_..._down` | `database.py` (new fn, registered at `MIGRATIONS_DOWN[12]`) | new | One-shot rollback |
| `entities.type`, `entities.kind`, `entities.lifecycle_class` | `entities` table | new schema | Polymorphic discriminator |
| `idx_entities_type_kind` | `entities` table | new index | Polymorphic-query workload |
| `entities.entity_type` | `entities` table | dropped | Replaced by `kind` |
| `entities_fts` (6 CREATE sites + sync INSERTs) | rewritten | modified | Search column changes to `kind` |
| `phase_events.event_type` CHECK | `phase_events` table | expanded 4→7 | New event types |
| `phase_events.metadata` (JSON TEXT, NULL-able) | `phase_events` table | new column | Event-specific payload |
| `phase_events.phase` NULL constraint | `phase_events` table | relaxed (NOT NULL → NULL-able) | New event types have no `phase` |
| `enforce_immutable_entity_type` trigger | `database.py` (6 sites) | removed | Blocks F11 backfill + F3 |
| `enforce_immutable_type_id` trigger | `database.py` (6 sites) | removed | Blocks F3 `type_id` rewrite |
| `EntityExistsError` | `database.py` (new class) | new | Raised by `register_entity` on conflict |
| `PromotionConflictError` | `database.py` (new class) | new | Raised by `promote_entity` on UNIQUE collision |
| `EntityDatabase.append_phase_event(...)` | `database.py` (new method, extends `insert_phase_event`) | new | Sole status-write entry point |
| `EntityDatabase.register_entity(...)` | `database.py:3343` | **behavior change** | Removes `INSERT OR IGNORE`; raises `EntityExistsError` |
| `EntityDatabase.upsert_entity(...)` | `database.py` (new method) | new | Idempotent insert-or-update with event emission |
| `EntityDatabase.promote_entity(...)` | `database.py` (new method) | new | Atomic UPDATE + event append |
| Doctor health check | `plugins/pd/hooks/lib/doctor/` (new check) | new | Static-grep audit at session start |
| Test helper `make_v12_db()` | `test_helpers.py` (new fn) | new | Versioned baseline for migration-12 tests |

### Sequencing inside the single migration

Migration 12 executes as one BEGIN IMMEDIATE transaction (with the `PRAGMA foreign_keys = OFF` outside per existing pattern). Inside the transaction, sub-steps run in this order:

1. **Pre-flight verification:** assert `schema_version == 11`, assert `pre-foreign_key_check` is empty, run AC-1.10 entity_id-collision audit (`SELECT ... INTERSECT ...`), log collisions to migration output (does not abort).
2. **AC-5.3 cleanup:** `DELETE FROM workflow_phases WHERE type_id = 'feature:'` (the one known malformed row); emit one-line audit log.
3. **F11 column additions:** `ALTER TABLE entities ADD COLUMN type TEXT NOT NULL DEFAULT 'work'`, same for `kind` (DEFAULT 'feature'), same for `lifecycle_class` (DEFAULT 'feature_flow'). The defaults are placeholders; backfill in step 4 corrects them.
4. **F11 backfill via UPDATE:** five UPDATEs (one per `entity_type → (type, kind, lifecycle_class)` mapping in spec FR-1 table). Defensive: assert every row's `entity_type` lands in the mapping (any unmapped row aborts the migration).
5. **F11 CHECK constraint via copy-rename:** rebuild `entities` with the new composite CHECK (the only way to add a CHECK in SQLite). Copy-rename pattern from `_expand_workflow_phase_check` migration 5 (`database.py:464-577`) is the template. **Critical ordering note:** the rebuilt `entities` table at this sub-step **retains the `entity_type` column** (still populated from the backfill in sub-step 4) — `entity_type` is NOT dropped until sub-step 8. This allows sub-step 6's FTS5 rebuild to read `entity_type` values while building the new `kind`-keyed FTS5 index (transition state). The `INSERT INTO entities_new SELECT uuid, workspace_uuid, type_id, entity_type, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, lifecycle_class FROM entities` preserves all columns. After the rebuild, the 12 trigger definitions across entities-recreation sites in the migration itself MUST exclude both `enforce_immutable_entity_type` and `enforce_immutable_type_id` (F11 + F3 simultaneous). All other triggers (`enforce_immutable_uuid`, `enforce_immutable_created_at`, `enforce_no_self_parent*`) ARE recreated on the rebuilt table — design contract: capture `SELECT sql FROM sqlite_master WHERE tbl_name='entities'` pre-migration to enumerate the trigger list, then recreate all minus the 2 immutable triggers.
6. **F11 FTS5 rebuild:** drop and recreate `entities_fts` with `kind` replacing `entity_type` in the column list. Use migration 4 (`database.py:421`) as the canonical template. Python backfill loop reads `entities.kind` (which is now populated by sub-step 4 backfill) and INSERTs into the new FTS5 table. (This sub-step is in **one place** in migration 12, not 6 places — the historical 6 are inside earlier `_migrate_*` functions that don't execute against current schema.)
7. **F11 readers rewrite:** in-source modifications (not done by migration, done by the implementation diff) — all production `entity_type` reads route through `kind`/`type` per AC-1.4.
8. **F11 column drop:** `ALTER TABLE entities DROP COLUMN entity_type` (SQLite 3.35+ supports this directly; if older, falls back to copy-rename — verify SQLite version at implement time).
9. **F11 index:** `CREATE INDEX idx_entities_type_kind ON entities(type, kind)`.
10. **F2 phase_events schema changes via copy-rename:**
    - Build `phase_events_new` with: expanded `event_type` CHECK (4 → 7 values), `phase` column NULL-able, new `metadata TEXT` column NULL-able.
    - `INSERT INTO phase_events_new SELECT id, type_id, project_id, phase, event_type, timestamp, iterations, reviewer_notes, backward_reason, backward_target, source, created_at, NULL AS metadata FROM phase_events`.
    - `DROP TABLE phase_events`, `ALTER TABLE phase_events_new RENAME TO phase_events`.
    - Recreate indexes (`idx_pe_lookup`, `idx_pe_project`, `idx_pe_timestamp`) and the `phase_events_backfill_dedup` partial-UNIQUE index.
11. **F3 (trigger removal already part of step 5):** runtime `DROP TRIGGER IF EXISTS enforce_immutable_entity_type` and `DROP TRIGGER IF EXISTS enforce_immutable_type_id` (idempotent guard for any orphan trigger that survived the entity-table rebuild).
12. **Post-flight verification:** assert `post-foreign_key_check` is empty, assert new schema rows count matches pre-migration count (minus AC-5.3 cleanup), stamp `schema_version = 12`.

The Python-side API additions (`upsert_entity`, `promote_entity`, `append_phase_event`, `EntityExistsError`, `PromotionConflictError`) ship in the same commit as the migration — but they are **separate code edits**, not part of the migration function body.

---

## 2. Technical Decisions

### TD-1: Path A (Python-layer enforcement of "status via events only") — confirmed from spec

The spec commits to Path A (FR-2). Design confirms: SQLite triggers cannot reliably detect cross-statement transactional state. The enforcement is three-pronged at the Python layer:

1. **Single sole-write helper** — `EntityDatabase.append_phase_event(...)` is the only public method that writes `entities.status` or `workflow_phases.workflow_phase`. (`register_entity`, `upsert_entity`, `promote_entity` all delegate to `append_phase_event` for their write step.)
2. **Static-grep CI test** — A new pytest test (`test_event_sourced_state.py::test_no_direct_status_updates`) runs `grep -rn 'UPDATE entities SET status' plugins/pd/hooks/lib/ plugins/pd/mcp/` and asserts the count is 0 outside the `append_phase_event` body. The test parses violations and prints the file:line of each.
3. **Doctor session-start audit** — A new doctor health check at `plugins/pd/hooks/lib/doctor/check_status_write_path.py` (or similar location) runs the same grep at SessionStart hook execution and emits a stderr warning if violations exist. Non-fatal.

**Why not SQL trigger:** reviewer iteration 2 correctly flagged that `sqlite_sequence` only tracks AUTOINCREMENT counters (not transaction-scoped queryable) and "transaction-local flag tables" require write-then-read which the trigger would itself need to intercept. The Python-layer approach catches violations at code-review and session-start time, which is sufficient for an internal codebase per the CLAUDE.md "private tooling" framing.

**Precedent:** `insert_phase_event` (`database.py:4630-4662`) already establishes the "sole write path" convention for `phase_events` insertions. The design extends this pattern to status writes.

### TD-2: Extend `insert_phase_event` rather than introduce a new `append_phase_event` symbol

The spec calls the new helper `append_phase_event`. The codebase already has `insert_phase_event` at `database.py:4630` as the sole write path to `phase_events`. Design decision: **rename the existing `insert_phase_event` to `append_phase_event`** (keeping the spec's terminology — "append" matches event-sourcing vocabulary better than "insert") and extend its signature to handle the new event types.

The rename is a single-commit step (commit 9 in spec NFR-3) with the new param surface. Call-site sizing: `grep -rn 'insert_phase_event(' plugins/pd/ | grep -v 'def insert_phase_event'` is run at implement time to enumerate every caller; expected count is the 4 internal backfill helper sites (`database.py:1587, 1603, 1630, 1657` per spec FR-4 audit table) plus any test fixtures. All such callers are renamed and parameter-shape-migrated in the same commit. This is consistent with the "no backward compat" project constraint.

**Scope acknowledgement:** the rename is an additional code-surface change beyond the spec's literal FR list. Spec FR-2 introduces `append_phase_event` as the new helper; design TD-2 chooses to consolidate by renaming the existing precedent rather than introducing a separate symbol. This is a design-phase scope choice (not a spec violation) — the choice is documented here for traceability.

**Alternative considered (rejected):** Keep both `insert_phase_event` (legacy phase-event-only) and `append_phase_event` (new, handles all event types). Rejected because: (a) two functions with overlapping intent create future ambiguity; (b) the spec's per-event-type column-domain table already specifies the unified signature; (c) the existing `insert_phase_event` callers are all in this feature's audit scope so the rename is bounded.

### TD-3: Migration is a single `BEGIN IMMEDIATE` transaction wrapping all sub-steps

The migration follows the established pattern (e.g. `_migration_11_workspace_identity`): one `BEGIN IMMEDIATE` covers all schema and data changes; `PRAGMA foreign_keys = OFF` is set OUTSIDE the transaction; `foreign_key_check` runs pre and post; `schema_version` is stamped INSIDE the transaction at the very end.

**Rationale:** atomicity is non-negotiable. If FTS5 rebuild succeeds but the CHECK expansion fails, we cannot leave the DB in a state where `entities` lacks `entity_type` but `entities_fts` references it. One transaction guarantees rollback to the pre-migration state on any failure.

**Performance:** the migration is small (~457 entity rows + ~78 brainstorm + ~167 backlog + 9 project + workflow_phases + phase_events copies = under 5000 rows total). Single-transaction is well within busy_timeout per NFR-1.

### TD-4: `EntityExistsError` and `PromotionConflictError` live in `database.py` (not a new `exceptions.py`)

**Rationale:** the codebase precedent (codebase-explorer findings) shows that custom exceptions live in their domain files (CycleError in dependencies.py, WorkspaceCorruptedError in project_identity.py, FrontmatterUUIDMismatch in frontmatter.py). No shared exceptions.py exists. Following the precedent keeps the codebase consistent.

**Base classes:** `EntityExistsError(ValueError)` and `PromotionConflictError(ValueError)`. Subclassing `ValueError` because both represent semantic-validation failures (duplicate key, identity collision), not runtime errors. The precedent exceptions follow this exact pattern.

**Attributes:**
- `EntityExistsError(workspace_uuid: str, type_id: str)` — both attributes accessible via `.workspace_uuid` and `.type_id` for caller inspection.
- `PromotionConflictError(workspace_uuid: str, old_type_id: str, new_type_id: str)` — three attributes.

### TD-5: `upsert_entity` follows the `upsert_workflow_phase` pattern (existing precedent at `database.py:4977-5077`)

`upsert_workflow_phase` is the existing INSERT OR IGNORE → upsert precedent. Its pattern: `INSERT OR IGNORE` to seed defaults, then unconditional `UPDATE` to set kwargs. Both inside `self.transaction()` (re-entrant context manager).

**Adaptation for `upsert_entity`:** the upsert semantics in the spec differ from `upsert_workflow_phase` in one key respect — `upsert_entity` emits a `phase_events` row on the insert branch and conditionally on the conflict branch (only on status change). So the pattern is:

```python
def upsert_entity(self, kind, entity_id, name, *, workspace_uuid=None, status=None, parent_uuid=None, parent_type_id=None, metadata=None, **other_kwargs) -> str:
    type_id = f"{kind}:{entity_id}"
    with self.transaction():
        # Try INSERT first via register_entity (which now raises on conflict)
        try:
            return self.register_entity(
                kind, entity_id, name,
                workspace_uuid=workspace_uuid, status=status,
                parent_uuid=parent_uuid, parent_type_id=parent_type_id,
                metadata=metadata, **other_kwargs,
            )
            # register_entity emits entity_created via append_phase_event internally
        except EntityExistsError:
            # Conflict path: read existing via the EXISTING public get_entity method
            existing = self.get_entity(type_id=type_id)  # database.py:3580
            if existing is None:
                # Should not happen — register raised EntityExistsError so a row must exist
                raise
            if existing['status'] == status or status is None:
                # No status change → no-op (do not UPDATE name/parent_uuid/metadata per spec FR-4 status-only rule)
                return existing['uuid']
            # Status changed → emit entity_status_changed event
            # append_phase_event INSERTs the event row AND updates entities.status + updated_at atomically
            self.append_phase_event(
                type_id=type_id,
                event_type='entity_status_changed',
                metadata={'old_status': existing['status'], 'new_status': status},
            )
            return existing['uuid']
```

**SQLite transaction semantics note (per "Pre-Research SQLite Transaction Facts at Design" memory):** A failed INSERT inside an explicit transaction does NOT auto-rollback the transaction in SQLite. When `register_entity` raises `EntityExistsError` (after catching the underlying `sqlite3.IntegrityError`), the outer `with self.transaction():` block remains open and in a clean state — the failed INSERT statement has been individually rejected by SQLite, but no implicit ROLLBACK was issued. The subsequent `get_entity` read and `append_phase_event` write therefore proceed normally within the same transaction. Reference: https://www.sqlite.org/lang_transaction.html.

`upsert_entity` does NOT update `name`, `parent_uuid`, or `metadata` on the conflict branch (per spec FR-4 corrected body and AC-4.4 — callers needing those use the existing `update_entity` API).

**Existing helpers used (not new):**
- `self.get_entity(type_id=...)` exists at `database.py:3580` — returns the entity dict or None.
- `self.get_entity_by_uuid(uuid)` exists at `database.py:2984` — returns the entity dict or None.
- No new private `_fetch_*` helpers are introduced — the design reuses these existing public methods.

### TD-6: `promote_entity` operation order and UNIQUE-safety pre-flight

```python
def promote_entity(self, uuid: str, new_kind: str, new_lifecycle_class: str, *, project_id=None) -> dict:
    with self.transaction():
        # Step 1: read existing via EXISTING public helper (not a new private method)
        existing = self.get_entity_by_uuid(uuid)  # database.py:2984
        if not existing:
            raise ValueError(f"Entity not found: {uuid}")

        # Step 2: derive new type_id (split on FIRST colon)
        old_type_id = existing['type_id']
        entity_id_suffix = old_type_id.split(":", 1)[1]  # everything after first colon
        new_type_id = f"{new_kind}:{entity_id_suffix}"

        # Step 3: UNIQUE-safety pre-flight (AC-3.6)
        if old_type_id != new_type_id:
            collision = self._conn.execute(
                "SELECT 1 FROM entities WHERE workspace_uuid = ? AND type_id = ? AND uuid != ?",
                (existing['workspace_uuid'], new_type_id, uuid)
            ).fetchone()
            if collision:
                raise PromotionConflictError(
                    workspace_uuid=existing['workspace_uuid'],
                    old_type_id=old_type_id,
                    new_type_id=new_type_id,
                )

        # Step 4: UPDATE entities (no enforce_immutable_* triggers — dropped in migration 12)
        self._conn.execute(
            "UPDATE entities SET kind = ?, lifecycle_class = ?, type_id = ?, updated_at = ? WHERE uuid = ?",
            (new_kind, new_lifecycle_class, new_type_id, iso_now(), uuid),
        )

        # Step 5: emit entity_promoted event (with new_type_id per design decision)
        self.append_phase_event(
            type_id=new_type_id,  # post-promotion identity (per spec FR-3 step 3 clarification)
            event_type='entity_promoted',
            metadata={
                'old_kind': existing['kind'],
                'new_kind': new_kind,
                'old_lifecycle_class': existing['lifecycle_class'],
                'new_lifecycle_class': new_lifecycle_class,
                'old_type_id': old_type_id,
                'new_type_id': new_type_id,
            },
        )

        # Step 6: return updated entity dict via EXISTING helper
        return self.get_entity_by_uuid(uuid)  # database.py:2984
```

The UNIQUE-safety pre-flight runs against the live row count (not a snapshot), and the read-then-write race is acceptable because the entire function is wrapped in `BEGIN IMMEDIATE` (via `self.transaction()`), so concurrent writers are serialized. SQLite's WAL mode + busy_timeout ensures no other connection can interleave.

### TD-7: FTS5 rebuild is one-shot inside migration 12 (not 6 places)

The 6 historical `CREATE VIRTUAL TABLE entities_fts` definitions live inside `_migrate_*` functions for prior schema epochs. Those functions are conditional on schema_version — they do NOT execute against the current schema during migration 12. Migration 12 contains exactly **one** new `entities_fts` rebuild block that runs against current state.

**Source-code cleanup:** the 6 historical definitions retain their `entity_type` references. This is **permitted** per spec AC-1.4 exception (b) ("the `_migrate_*` historical migration functions in `database.py` that document past schema epochs"). Removing them would alter the historical record of the migration sequence — an anti-pattern called out in CLAUDE.md.

**What migration 12 changes:** only its own new FTS5 CREATE block, and the production-path INSERT/DELETE statements at `database.py:3469, 5544, 3874, 4142` (the runtime sync paths, not the historical schema-creation paths). Per AC-1.8's grep-predicate verification.

### TD-8: Reader rewrites (AC-1.4) are mechanical and bounded

The audit boundary in AC-1.4 says `grep -rn '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/` returns 0 production references, with explicit exceptions for migration functions and test fixtures. Design decision: do this rewrite as **a single commit per file**, not as a single mega-commit, so each file's rewrite is independently bisectable. Concretely: one commit per affected file under `plugins/pd/hooks/lib/entity_registry/` and `plugins/pd/mcp/`.

The list of affected files comes from `grep -rln '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/` filtered to non-migration, non-test sites. Expected ~6-10 files based on the codebase-explorer findings.

### TD-9: Reverse migration (MIGRATIONS_DOWN[12]) is implemented but one-shot

Following the precedent set by `_migration_11_workspace_identity_down`, migration 12 also has a down-migration. It is **one-shot** per spec AC-5.1 — running `up → down → up` is not supported. The down restores one canonical trigger per name (not all 6), narrows the `phase_events.event_type` CHECK, removes the new columns, re-adds `entity_type`, and reverts the FTS5 column.

The reverse migration is tested on a copy-of-live-DB scenario in `test_migration_12_safety.py` (per AC-5.1 and the test_helpers.py precedent).

### TD-10: Doctor health check placement

Two reasonable locations: (a) inside `plugins/pd/hooks/lib/doctor/` (existing doctor surface — verify via `ls plugins/pd/hooks/lib/doctor/`), or (b) as a new `plugins/pd/hooks/lib/doctor/check_event_sourcing.py` file. Design picks **(a) extend existing doctor** — keeps related health checks together. The new check is registered in the doctor's check registry (look for the registry at implement time; likely `plugins/pd/hooks/lib/doctor/__init__.py` or `doctor.py`).

**Behavior:** the check runs `grep -nE 'UPDATE entities SET status|INSERT OR IGNORE INTO entities' plugins/pd/hooks/lib/ plugins/pd/mcp/` (excluding migration helpers and the `append_phase_event` body) and emits a stderr warning on any match. Non-fatal — doctor returns 0 on warnings, non-zero only on hard failures.

---

## 3. Interfaces

### 3.1 Database class additions

#### `EntityDatabase.register_entity` (behavior change)

The post-feature-109 signature **preserves the existing positional shape** at `database.py:3343` — the first positional parameter is renamed from `entity_type` to `kind` (per F11), all other parameters unchanged including the keyword-only `parent_type_id` deprecated alias:

```python
def register_entity(
    self,
    kind: str,           # post-F11: was `entity_type`; one of {feature, backlog, project, brainstorm, workspace}
    entity_id: str,
    name: str,
    *,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    parent_type_id: str | None = None,  # deprecated alias kept for transition compat (feature 108 introduced; cleanup deferred to 110+)
    metadata: dict | None = None,
) -> str:
    """
    Register a new entity. Raises EntityExistsError on (workspace_uuid, type_id) conflict.

    Internally:
    - Derives `type` from `kind` via the F11 mapping table (kind 'feature'/'backlog' → type 'work', etc.).
    - Derives `lifecycle_class` from `kind` (per F11 mapping).
    - Builds `type_id` as f"{kind}:{entity_id}".

    Returns the new entity's uuid.

    Side effects:
    - INSERT INTO entities (no INSERT OR IGNORE; raises EntityExistsError on conflict)
    - INSERT INTO entities_fts (FTS5 sync)
    - append_phase_event(type_id, 'entity_created', metadata={...creation context...})

    Raises:
    - EntityExistsError: if (workspace_uuid, type_id) already exists in entities.
    """
```

**Parameter shape continuity:** the rename `entity_type → kind` is mechanically backward-compatible for callers that pass the parameter positionally (e.g. `register_entity('feature', '042-foo', 'My Feature')`). Callers that pass `entity_type=` as a kwarg will TypeError; per the FR-4 Python-caller audit table, the 17 production call sites are visited in the implementation diff and updated as part of the routing decision (either renamed to `kind=` or kept positional). Tests under `plugins/pd/hooks/lib/entity_registry/tests/` that pass `entity_type=` are similarly updated.

**`parent_type_id` deprecated alias:** kept as-is (no behavior change in this feature). It was introduced by feature 108 as a transition tool and will be removed by feature 110+. The implementation diff does NOT touch this parameter. Caller audit: `grep -rn 'parent_type_id=' plugins/pd/` at implement time confirms current usage; if zero, the parameter can be safely dropped instead (decision deferred to implementer per the spec FR-4 audit-at-implement-time pattern).

**Breaking change:** previously silently no-op'd on conflict; now raises `EntityExistsError`. Callers per the FR-4 Python-caller audit table either explicitly catch `EntityExistsError` (when conflict-is-real-error) or migrate to `upsert_entity`.

#### `EntityDatabase.upsert_entity` (new)

```python
def upsert_entity(
    self,
    kind: str,
    entity_id: str,
    name: str,
    *,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    parent_type_id: str | None = None,  # deprecated alias, same as register_entity
    metadata: dict | None = None,
) -> str:
    """
    Idempotent insert-or-status-update. Signature byte-identical to register_entity.

    Insert branch (no conflict): same as register_entity (emits entity_created event).
    Conflict + status change: emits entity_status_changed event; updates status + updated_at only.
    Conflict + no status change: no-op.

    Returns the entity's uuid in all branches.

    Does NOT update name, parent_uuid, or metadata on conflict — callers needing those
    use the existing update_entity API. (Aligns with spec FR-4 / AC-4.4 after the
    iteration-1-of-design cross-phase patch to spec FR-4 body.)
    """
```

Signature is byte-identical to `register_entity` (per AC-4.3 — verified at implement time via `inspect.signature` equality assertion).

#### `EntityDatabase.promote_entity` (new)

```python
def promote_entity(
    self,
    uuid: str,
    new_kind: str,
    new_lifecycle_class: str,
    *,
    project_id: str | None = None,
) -> dict:
    """
    Atomic kind/lifecycle_class change with type_id prefix rewrite.

    Single transaction:
    1. UNIQUE-safety pre-flight: if new_type_id collides with an existing row in the
       same workspace, raise PromotionConflictError.
    2. UPDATE entities SET kind, lifecycle_class, type_id, updated_at WHERE uuid.
    3. append_phase_event(new_type_id, 'entity_promoted', metadata={old_*, new_*}).

    Returns the updated entity row as a dict.

    Raises:
    - PromotionConflictError: if (workspace_uuid, new_type_id) already exists.
    - ValueError: if uuid does not resolve to an entity.

    Note: the `enforce_immutable_entity_type` and `enforce_immutable_type_id` triggers
    are dropped in migration 12, so this UPDATE succeeds without trigger interference.
    """
```

#### `EntityDatabase.append_phase_event` (renamed from `insert_phase_event`; extended)

```python
def append_phase_event(
    self,
    type_id: str,
    event_type: str,  # one of 7: started|completed|skipped|backward|entity_created|entity_status_changed|entity_promoted
    *,
    project_id: str | None = None,
    phase: str | None = None,  # required for the 4 workflow event types; must be None for the 3 entity event types
    iterations: int | None = None,  # required for 'completed' only; must be None otherwise
    reviewer_notes: str | None = None,  # optional for workflow events; must be None for entity events
    backward_reason: str | None = None,  # required for 'backward' only
    backward_target: str | None = None,  # required for 'backward' only
    metadata: dict | None = None,  # required for 'entity_status_changed' and 'entity_promoted'; optional for 'entity_created'; must be None for workflow events
    source: str = 'live',
    timestamp: str | None = None,  # auto-generated via _iso_now() when None; tests inject controlled timestamps for deterministic ordering assertions (AC-2.2, AC-2.7)
) -> int:
    """
    Sole write path for phase_events INSERTs.

    Validates per-event-type column-domain (see spec FR-2 mapping table).
    Inside one transaction:
    1. INSERT INTO phase_events (...) returning id
    2. For entity_* event types: UPDATE entities SET status, updated_at WHERE type_id = ?
    3. For workflow event types: UPDATE workflow_phases SET workflow_phase, updated_at WHERE type_id = ?

    Returns the new phase_events row id.

    Raises:
    - ValueError: if param shape does not match event_type's column-domain (e.g. 'iterations'
      passed with event_type='entity_created').
    """
```

**Validation table** (per spec FR-2 column-domain mapping):

```python
_VALID_PARAMS = {
    'started':              {'phase'},
    'completed':            {'phase', 'iterations', 'reviewer_notes'},
    'skipped':              {'phase'},
    'backward':             {'phase', 'reviewer_notes', 'backward_reason', 'backward_target'},
    'entity_created':       {'metadata'},
    'entity_status_changed':{'metadata'},  # metadata REQUIRED, not just allowed
    'entity_promoted':      {'metadata'},  # metadata REQUIRED, not just allowed
}
_REQUIRED_PARAMS = {
    'completed':            {'phase', 'iterations'},
    'backward':             {'phase', 'backward_reason', 'backward_target'},
    'entity_status_changed':{'metadata'},
    'entity_promoted':      {'metadata'},
}
```

If `event_type` is invalid, `KeyError` rather than `ValueError` is appropriate (raised at dict lookup). If params do not satisfy `_VALID_PARAMS` (irrelevant param passed) or `_REQUIRED_PARAMS` (required param missing), raise `ValueError` with a clear message naming the violation.

### 3.2 Exception classes

```python
# In database.py, near the top with other module-level definitions

class EntityExistsError(ValueError):
    """Raised by register_entity when (workspace_uuid, type_id) conflict occurs."""
    def __init__(self, workspace_uuid: str, type_id: str):
        super().__init__(f"Entity already exists: workspace_uuid={workspace_uuid!r}, type_id={type_id!r}")
        self.workspace_uuid = workspace_uuid
        self.type_id = type_id


class PromotionConflictError(ValueError):
    """Raised by promote_entity when the post-promotion type_id collides with an existing row."""
    def __init__(self, workspace_uuid: str, old_type_id: str, new_type_id: str):
        super().__init__(
            f"Promotion would create a UNIQUE conflict: workspace_uuid={workspace_uuid!r}, "
            f"old_type_id={old_type_id!r}, new_type_id={new_type_id!r} (already exists)"
        )
        self.workspace_uuid = workspace_uuid
        self.old_type_id = old_type_id
        self.new_type_id = new_type_id
```

### 3.3 Migration function

```python
def _migration_12_polymorphic_taxonomy_and_events(conn: sqlite3.Connection) -> None:
    """Migration 12: polymorphic taxonomy + event-sourced state.

    Follows the established pattern (PRAGMA foreign_keys OFF outside; BEGIN IMMEDIATE
    inside try; foreign_key_check pre/post; schema_version stamped inside transaction).

    See: docs/features/109-polymorphic-taxonomy-and-event/{spec.md,design.md}.
    """
    # Idempotency double-check (per migration 10 / 11 pattern)
    v_row = conn.execute(
        "SELECT value FROM _metadata WHERE key = 'schema_version'"
    ).fetchone()
    if v_row and int(v_row[0]) >= 12:
        return

    # PRAGMA foreign_keys must be OFF for ALTER TABLE / DROP COLUMN / copy-rename
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        fk_state = conn.execute("PRAGMA foreign_keys").fetchone()
        if not fk_state or int(fk_state[0]) != 0:
            raise RuntimeError("Migration 12: PRAGMA foreign_keys = OFF failed")

        conn.execute("BEGIN IMMEDIATE")
        try:
            # Idempotency re-check inside transaction (per migration 10 pattern)
            v_row = conn.execute("SELECT value FROM _metadata WHERE key = 'schema_version'").fetchone()
            if v_row and int(v_row[0]) >= 12:
                conn.execute("ROLLBACK")
                return

            # Step 1: pre-flight FK check
            pre_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if pre_violations:
                raise RuntimeError(f"Migration 12 pre-FK violations: {pre_violations}")

            # Step 1b: AC-1.10 entity_id collision audit (informational, non-blocking)
            collisions = conn.execute(...)  # SELECT ... INTERSECT ... per spec AC-1.10
            for c in collisions:
                print(f"INFO: Migration 12 pre-flight collision detected: workspace={c[0]}, suffix={c[1]}", file=sys.stderr)

            # Step 2: AC-5.3 cleanup
            conn.execute("DELETE FROM workflow_phases WHERE type_id = 'feature:'")

            # Step 3: F11 columns + backfill (see sub-steps 3-8 in §1)
            ...

            # Step 9: F2 phase_events copy-rename (see sub-step 10 in §1)
            ...

            # Step 10: Stamp schema_version
            conn.execute(
                "INSERT OR REPLACE INTO _metadata(key, value) VALUES ('schema_version', '12')"
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    # Post-flight FK check (outside transaction, per pattern)
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(f"Migration 12 post-FK violations: {post_violations}")
```

The `...` placeholders are intentional design omissions — the implementation phase fills them with the SQL/Python per spec FR-1, FR-2, FR-3 and the sub-step order in §1. Design contract is that **each sub-step is in this function body**, not split across helpers (matches `_migration_11_workspace_identity` pattern).

### 3.4 Test helper

```python
# In test_helpers.py

def make_v12_db(path=None):
    """
    Build a raw sqlite3.Connection at exactly schema_version=12 by running
    MIGRATIONS[v] for v in 1..12.

    Mirrors make_v10_db / make_v11_db. Used for RED tests verifying migration 13+
    (future) and as a stable baseline for feature-109 integration tests.
    """
    conn = make_v11_db(path)
    MIGRATIONS[12](conn)
    return conn
```

### 3.5 MCP error contracts

The MCP `register_entity` tool surface (3 call sites in `plugins/pd/mcp/entity_server.py` per spec FR-4 audit) translates `EntityExistsError` and `PromotionConflictError` to structured JSON errors. The shape mirrors the existing MCP error pattern in `entity_server.py` (verify exact shape at implement time; if no precedent, use this design contract):

**`EntityExistsError` → MCP response:**
```json
{
  "error": true,
  "error_type": "entity_exists",
  "message": "Entity already exists: workspace_uuid='...', type_id='...'",
  "workspace_uuid": "...",
  "type_id": "...",
  "recovery_hint": "Use upsert_entity for idempotent registration, or check workspace context."
}
```

**`PromotionConflictError` → MCP response:**
```json
{
  "error": true,
  "error_type": "promotion_conflict",
  "message": "Promotion would create a UNIQUE conflict: workspace_uuid='...', old_type_id='...', new_type_id='...' (already exists)",
  "workspace_uuid": "...",
  "old_type_id": "...",
  "new_type_id": "...",
  "recovery_hint": "Resolve the existing entity at new_type_id before promoting, or pick a different new_kind."
}
```

Both error shapes follow the existing MCP error convention: `{"error": true, "error_type": "...", "message": "...", "recovery_hint": "..."}` with feature-specific fields appended. Skills/commands that call these MCP tools parse `error_type` for branching.

The MCP tool error contracts are public — once shipped, future skill/command code may depend on them. Locking them in design (rather than deferring to plan) prevents downstream churn.

### 3.6 Doctor check

```python
# In plugins/pd/hooks/lib/doctor/ (extends existing doctor surface)

def check_status_write_path() -> list[str]:
    """
    Doctor health check: assert no production code writes entities.status directly.

    Returns a list of violation strings (file:line:content). Empty list = OK.
    """
    import subprocess
    result = subprocess.run(
        ['grep', '-rnE',
         r'UPDATE entities SET status|INSERT OR IGNORE INTO entities',
         'plugins/pd/hooks/lib/', 'plugins/pd/mcp/'],
        capture_output=True, text=True
    )
    # Filter out the permitted exceptions (migration functions, test fixtures, append_phase_event body)
    violations = []
    for line in result.stdout.splitlines():
        if '_migrate_' in line or 'test_' in line or 'append_phase_event' in line:
            continue
        violations.append(line)
    return violations
```

The doctor check is wired into the existing doctor registry (verify exact mechanism at implement time).

---

## 4. Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| FTS5 rebuild Python loop fails mid-backfill | Low | High (FTS5 inconsistent with entities) | Single-transaction wrapping ensures FTS5 rebuild rolls back with entities if anything fails. Tested on copy-of-live-DB. |
| WAL lock held by another process during migration | Medium | High (migration aborts) | Established pattern: pre-migration check for stale processes (CLAUDE.md SQLite lock recovery); helpful error message. Doctor session-start check already kills stale MCP processes. |
| `entity_type` reader rewrite misses a call site | Medium | Medium (runtime AttributeError on column-not-found) | AC-1.4 grep verification at completion; mechanical per-file commit makes the bisect-bug obvious. |
| `register_entity` callers expecting silent ignore now raise unhandled `EntityExistsError` | High | High (production failures) | Spec AC-4.8 audits all ~17 production callers with explicit routing decision; per-caller code comments and tests verify behavior. The 17-site audit is the load-bearing safety net. |
| `promote_entity` UNIQUE-safety pre-flight has a race with concurrent writers | Low | Medium (PromotionConflictError on legitimate promotion) | Wrap in `BEGIN IMMEDIATE` (re-entrant `self.transaction()`); SQLite WAL + busy_timeout serializes writers. |
| Down-migration restores only 1 trigger but up-migration left 6 sites cleaned | Low | Medium (up → down → up cycle fails) | Documented as one-shot rollback (spec AC-5.1 + design TD-9); operator-facing constraint. |
| New `phase_events.metadata` JSON column is read by code that assumes it's TEXT | Low | Low | Storage type is TEXT (JSON1 functions work over TEXT); readers use `json.loads` explicitly. |
| Migration 12 conflicts with another in-flight migration (e.g. 11) due to concurrent runners | Very low | High | Idempotency double-check inside transaction (per migration 10/11 pattern) early-returns if schema_version already advanced. |
| AC-2.1 Python-layer enforcement misses a bypass via raw cursor access | Medium | Medium | Static grep + doctor session-start audit catches violations at code-review / session-start. Spec §6 acknowledges this as accepted residual risk. |
| Mid-flight test coverage gap on the FTS5 rebuild | Medium | High (search semantics break for users) | New `test_polymorphic_taxonomy.py::test_fts5_search_kind_matches_legacy_entity_type` asserts that `entities_fts MATCH 'kind:work'` returns the same rows that previously matched `entity_type:feature` + `entity_type:backlog` combined. |

---

## 5. Open Questions (for plan phase)

These are HOW questions for the plan phase, not blocking design completion:

1. **Doctor check registry location** — verify at implement time the exact file where doctor health checks are registered (likely `plugins/pd/hooks/lib/doctor/__init__.py` or `doctor.py`).
2. **`SQLite version check` for ALTER TABLE DROP COLUMN** — verify whether the production environment runs SQLite 3.35+ (which supports DROP COLUMN directly). If not, fall back to copy-rename for the `entity_type` column drop. Empirical check at implement time: `>>> import sqlite3; sqlite3.sqlite_version → '3.35.0'` or later — most macOS 13+ ships with 3.39+.
3. **Reader rewrite file list** — `grep -rln '\bentity_type\b' plugins/pd/hooks/lib/ plugins/pd/mcp/` (filtered to non-migration, non-test). Expected ~6-10 files; exact list captured by the plan phase.
4. **MCP entity_server.py error contract precedent** — verify at implement time that the JSON shape in §3.5 matches the existing MCP error pattern in entity_server.py. The contract values are locked in §3.5; only the format (e.g., `error_type` vs `error_kind` key name) may shift to match precedent.

---

## 6. Prior Art Research

### Codebase patterns reused (per Step 0 research)

- **Migration calling convention** (`database.py:5602-5622` `_migrate`): versioned dict `MIGRATIONS[v]`, schema_version in `_metadata` table (not PRAGMA user_version), idempotency double-check at start.
- **Migration transaction pattern** (`database.py:170-325, 464-577`): PRAGMA foreign_keys=OFF outside try, BEGIN IMMEDIATE inside, foreign_key_check pre/post, schema_version stamped inside transaction.
- **CHECK constraint expansion via copy-rename** (`database.py:464-577` `_expand_workflow_phase_check` / migration 5): template for widening CHECK enum.
- **FTS5 rebuild template** (`database.py:421` migration 4 `_create_fts_index`): CREATE VIRTUAL TABLE entities_fts USING fts5(...) + Python backfill loop.
- **EntityDatabase class** (`database.py:2720` class definition, line 2735 `__init__`): WAL mode + busy_timeout=15000 + cache_size=-8000 + FK=ON via `_set_pragmas()`. Reusing the existing class.
- **`transaction()` context manager** (`database.py:3186`): re-entrant; suppresses inner `_commit()` calls via `_in_transaction` flag. Preferred for new methods (NOT `begin_immediate` which is deprecated).
- **upsert pattern precedent** (`database.py:4977-5077` `upsert_workflow_phase`): INSERT OR IGNORE seed + unconditional UPDATE. Adapt for `upsert_entity` with event emission.
- **Custom exception convention**: per-domain (CycleError in dependencies.py, WorkspaceCorruptedError in project_identity.py, FrontmatterUUIDMismatch in frontmatter.py). New exceptions in `database.py`.
- **Test fixture pattern** (`test_database_052.py:29-34`): `EntityDatabase(':memory:')` yields db, close on teardown.
- **Versioned baseline helper** (`test_helpers.py:55-109` `make_v10_db`): build raw `sqlite3.Connection` at specific schema version by iterating MIGRATIONS[1..N]. Add `make_v12_db`.
- **"Sole write path" precedent** (`database.py:4630-4662` `insert_phase_event`): existing sole-writer convention for phase_events. Rename to `append_phase_event` and extend signature.
- **Down-migration pattern** (`database.py:2637, 2642-2703`): MIGRATIONS_DOWN registry. Add entry for migration 12.

### External patterns

Internet research skipped per YOLO mode — codebase patterns are well-established and the architectural moves (event sourcing, polymorphic taxonomy via discriminator columns) are well-documented elsewhere; no new external evidence is load-bearing for this design.

---

## 7. Memory Influence

Memory entries surfaced during pre-design research:
- **Atomic commit discipline in schema migrations** (high) — applied: NFR-3 16-step commit sequence in spec; design TD-3 confirms single-transaction migration.
- **Pre-Research SQLite Transaction Facts at Design** (high) — applied: TD-3 documents the foreign_keys OFF / BEGIN IMMEDIATE / foreign_key_check pre+post pattern explicitly with code citations.
- **UNIQUE constraint migration requires FK dependency audit** (high) — applied: AC-3.6 + TD-6 promote_entity UNIQUE-safety pre-flight; AC-1.10 entity_id collision audit pre-migration.
- **Security Injection Enumeration for Migration Tools Touching SQLite** (high) — N/A: this migration does not accept external SQL input.
- **Dual status fields without cross-table sync guarantees drift** (high, from specify-phase refresh) — applied: this design's primary purpose is exactly to PREVENT this drift by making `phase_events` the single state-change primitive and `entities.status` / `workflow_phases.workflow_phase` projections.
- **two-pivot-design-escalation** (heuristic, from specify-phase refresh) — noted: design is on its first pass; no pivots have occurred. Will escalate if reviewer iteration triggers >2 architectural pivots.
- **Enumerate Git Edge Cases in Design Technical Decisions** (pattern) — N/A: no git operations in this design.

---

## 8. Glossary (terms used in this design beyond the spec)

- **Idempotency double-check**: pattern from migration 10/11 — re-read schema_version as the first statement inside the BEGIN IMMEDIATE transaction; early-return if already at target version. Guards against concurrent migration runners.
- **Copy-rename pattern**: SQLite idiom for schema changes that ALTER TABLE doesn't support directly (CHECK expansion, column drop on older SQLite, NOT NULL relaxation). Create new table with target schema, INSERT-SELECT, DROP old, RENAME new.
- **`_metadata` table**: the canonical store for `schema_version` and other migration metadata. Distinct from SQLite's built-in `PRAGMA user_version` (not used by this codebase).
