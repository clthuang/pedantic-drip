# Specification: Unify Entity Reconciliation

**Origin:** Ad-hoc discovery from DB audit showing 96 stale backlog entities with duplicates, null statuses, and junk entries. Related: backlog #00040.

## Problem Statement
Entity reconciliation is split across two modules with a critical gap: `entity_status.py` syncs features/projects from `.meta.json`, `brainstorm_registry.py` registers brainstorms from `.prd.md` files, but **no module syncs backlogs** from `backlog.md`. This leaves backlog entity statuses permanently stale in the DB — closed items show as "open", promoted items aren't updated, and junk entries from cross-project backlogs accumulate (96 backlog entities in DB, many duplicates with null status).

## Success Criteria
- [ ] All entity types (features, projects, brainstorms, backlogs) are reconciled by a single unified function
- [ ] Backlog items marked as closed/promoted/fixed in `backlog.md` have their DB status updated accordingly
- [ ] Junk backlog entities (non-5-digit IDs, OCM checklist items) are deleted from DB
- [ ] Duplicate backlog entities (same ID, same project) are deduplicated
- [ ] `brainstorm_registry.py` module is removed — its logic absorbed into the unified function
- [ ] Existing reconciliation behavior for features/projects is preserved (zero regression)
- [ ] Reconciliation runs at session start (existing trigger, no change)

## Write Ownership
- `backlog.md` is the **source of truth** for backlog entity status
- The reconciliation orchestrator is the **sole writer** of backlog entity statuses in the DB
- Manual MCP `update_entity` calls for backlog status will be overwritten on next reconciliation run
- This matches the existing pattern: `.meta.json` is source of truth for features/projects

## API Change
`sync_entity_statuses()` gains an `artifacts_root` parameter (relative path like `"docs"`) needed for brainstorm registration (currently only in `brainstorm_registry.py`).

New signature: `sync_entity_statuses(db, full_artifacts_path, project_id, artifacts_root)`

Return dict gains `registered` count (for new brainstorms/backlogs): `{"updated": int, "skipped": int, "archived": int, "registered": int, "deleted": int, "warnings": list[str]}`

## Backlog Status Mapping

| backlog.md marker | DB status | Rationale |
|---|---|---|
| `(closed:` any reason including "merged into") | `dropped` | All closures map to dropped — "merged into" is a closure variant, not a promotion |
| `(promoted →` | `promoted` | Explicitly promoted to feature/project |
| `(fixed:` | `dropped` | Fix applied — same as closure |
| No marker | `open` | Default for items without status text |

These statuses must be added to backlog entity validation. The existing feature STATUS_MAP (`active`, `completed`, `abandoned`, `planned`, `promoted`) does not apply to backlogs — backlogs use their own status vocabulary defined in ENTITY_MACHINES: `open`, `triaged`, `promoted`, `dropped`.

## Scope

### In Scope
- Merge `brainstorm_registry.sync_brainstorm_entities()` logic into `sync_entity_statuses()` — this is a code merge, not new functionality
- Add brainstorm status management (NEW functionality): detect missing `.prd.md` files for registered brainstorms and update status to "archived"
- Add backlog sync: parse `backlog.md` table rows, detect status markers, update DB
- Delete junk entities: remove DB rows with non-5-digit backlog IDs (active cleanup, not passive ignore)
- Deduplicate: when same backlog ID has multiple DB rows within the same project, keep the one with non-null status and delete the other
- Update `reconciliation_orchestrator/__main__.py` to remove Task 2 (brainstorm_registry) call, pass `artifacts_root` to Task 1
- Delete `brainstorm_registry.py` after merge

### Out of Scope
- Restructuring entity metadata from JSON blob to structured tables (backlog #00051)
- Cross-project entity deduplication (different project_id, same entity_id) — AC-7 only handles same-project duplicates
- Backlog workflow phase tracking (backlogs use simple status, not workflow phases)
- Changing how `backlog.md` is formatted or maintained

## Acceptance Criteria

### AC-1: Unified sync function handles all 4 entity types
- Given `sync_entity_statuses(db, full_artifacts_path, project_id, artifacts_root)` is called
- When it scans the artifacts directory
- Then it syncs features (from `.meta.json`), projects (from `.meta.json`), brainstorms (from `.prd.md` files), and backlogs (from `backlog.md`)
- And returns `{"updated": N, "skipped": N, "archived": N, "registered": N, "deleted": N, "warnings": [...]}`

### AC-2: Backlog status detection from markdown
- Given `backlog.md` contains a row `| 00014 | ... (closed: reason) |`
- When backlog sync runs
- Then entity `backlog:00014` status is updated to `"dropped"` in the DB

### AC-3: Backlog promotion detection
- Given `backlog.md` contains a row `| 00027 | ... (promoted → feature:068-simplify-secretary-modes) |`
- When backlog sync runs
- Then entity `backlog:00027` status is updated to `"promoted"` in the DB

### AC-4: Backlog fixed detection
- Given `backlog.md` contains a row with `(fixed: reason)`
- When backlog sync runs
- Then entity `backlog:{id}` status is updated to `"dropped"` in the DB

### AC-5: Open backlog items registered
- Given `backlog.md` contains a row with no status marker (no `(closed:`, `(promoted →`, `(fixed:`)
- When backlog sync runs and entity doesn't exist in DB
- Then a new entity is registered with `entity_type="backlog"`, `entity_id={5-digit ID}`, `name={description text from row}`, `artifact_path="{artifacts_root}/backlog.md"`, `status="open"`, `project_id={current project}`
- And `registered` count is incremented

### AC-6: Junk entity deletion
- Given the DB contains `backlog:B2`, `backlog:#`, `backlog:~~B1~~` (non-5-digit IDs)
- When backlog sync runs
- Then these entities are **deleted** from the DB (valid backlog IDs match regex `^[0-9]{5}$` — exactly 5 digits, zero-padded; anything else is junk)
- And `deleted` count is incremented for each

### AC-7: Same-project duplicate deduplication
- Given `backlog:00020` appears twice in the DB with the **same project_id**
- When reconciliation runs
- Then only one entity remains (preferring the one with non-null status)
- And `deleted` count is incremented for each removed duplicate
- Note: cross-project duplicates (different project_id) are left as-is (out of scope)

### AC-8: Brainstorm registration absorbed
- Given `brainstorm_registry.py` is deleted
- When reconciliation orchestrator runs
- Then new brainstorms (`.prd.md` files without DB entries) are registered with `status: "active"` (Note: "active" is outside brainstorm ENTITY_MACHINES which uses draft/reviewing/promoted/abandoned — this matches existing brainstorm_registry.py behavior. Reconciliation uses db.register_entity directly, not the workflow phase transition API.)
- And `registered` count is incremented

### AC-9: Brainstorm missing file detection
- Given a brainstorm entity exists in the DB but its `.prd.md` file no longer exists
- When brainstorm sync runs
- Then the brainstorm entity status is set to `"archived"` (file deleted — could be promotion, cleanup, or manual removal; "archived" is the safe generic status)

### AC-10: Zero regression for feature/project sync
- Given existing features and projects with `.meta.json` files
- When the unified sync runs
- Then the feature/project portion produces identical values for the `updated`/`skipped`/`archived`/`warnings` keys as the current `sync_entity_statuses()` for the same input. The new `registered`/`deleted` keys are additive and do not affect feature/project counts.

### AC-11: Orchestrator updated
- Given `reconciliation_orchestrator/__main__.py`
- When it runs
- Then Task 2 (brainstorm_registry) is removed
- And Task 1 call passes `artifacts_root` as additional parameter
- And the output JSON reports a single `entity_sync` key covering all 4 entity types

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** All source data is already available (`.meta.json`, `.prd.md`, `backlog.md`). The existing `sync_entity_statuses` function provides the pattern. Backlog parsing is regex on a markdown table — well-understood. The merge is additive — features/projects behavior unchanged.

**Key Assumptions:**
- `backlog.md` uses consistent format: `| {5-digit ID} | {timestamp} | {description with status markers} |` — Status: Verified from backlog.md
- Status markers are: `(closed:`, `(promoted →`, `(fixed:` — Status: Verified from backlog.md
- Junk entries have non-5-digit IDs (B2, #, ~~B1~~) — Status: Verified from DB export
- Backlog ENTITY_MACHINES defines valid statuses: open, triaged, promoted, dropped — Status: Verified from entity_lifecycle.py

## Dependencies
- `entity_registry/database.py` — EntityDatabase API (register_entity, update_entity, get_entity, delete_entity)
- `entity_registry/entity_lifecycle.py` — ENTITY_MACHINES backlog status definitions
- `reconciliation_orchestrator/__main__.py` — orchestrator entry point
- `backlog.md` — source of truth for backlog status

## Open Questions (Resolved)
- ~~Should AC-9 (brainstorm without .prd.md) set status to "promoted" or "archived"?~~ → Resolved: "archived" — file absence is ambiguous (could be promotion, cleanup, or manual deletion). "archived" is the safe generic status. If the brainstorm was promoted to a feature, the `brainstorm_source` field in the feature's `.meta.json` provides the linkage.
