# PRD: Reactive Entity Consistency Engine

**Date:** 2026-03-20
**Status:** Draft
**Source:** [pd-plugin-gap-analysis.md](/Users/terry/Downloads/pd-plugin-gap-analysis.md) — field feedback from cast-below (21 features, 1 project, 57% .meta.json data gaps)

---

## Problem Statement

The pd plugin was designed as a **single-entity, forward-only workflow tracker**. It excels at walking one feature through brainstorm-to-finish. But at scale (21+ features, cross-project relationships, dependency graphs, lifecycle transitions), three architectural mismatches produce 12 user-facing gaps:

1. **Multiple independent truth stores** — `entities.status`, `workflow_phases.kanban_column`, `workflow_phases.last_completed_phase`, and `.meta.json` each claim authority over "is this feature done?" They're set by different code paths at different times, diverge silently, and give different answers to the same query. (Gaps 3, 5, 8, 12)

2. **No reactive consistency** — entities are independent islands. Completing a project doesn't unblock its downstream features. Deleting a brainstorm doesn't archive its entity. Ghost entities accumulate because nothing reacts to filesystem changes. The global DB mixes entities from all workspaces because nothing scopes queries. (Gaps 1, 4, 6, 10)

3. **No operational flexibility** — one rigid phase sequence for all feature types. Guards block legitimate maintenance with no override path. No validation on creation, no verification on completion. (Gaps 2, 7, 9, 11)

**The common root cause:** pd treats each entity mutation as an isolated write. There is no concept of "when X changes, also update Y." Every cross-entity concern is deferred to periodic reconciliation, which is incomplete, silent, and unidirectional.

**Evidence:**
- 57% of `.meta.json` files had data gaps (cast-below audit) — Assumption: field validation absent
- 4 features stuck with `kanban_column=backlog` despite `status=completed` — Evidence: `reconcile_apply` doesn't fix kanban drift
- Feature 006 remained `blocked` after its blocker was completed — Evidence: no cascading reference updates
- 7 ghost entities from another workspace in cast-below's registry — Evidence: `~/.claude/pd/entities/entities.db` is global with no workspace filter
- `reconcile_status` permanently reports `healthy: false` due to 83 frontmatter drift entries — Evidence: frontmatter was never implemented but check was added

---

## Solution: Reactive Entity Consistency Engine (RECE)

### Design Philosophy

Replace the current "write then periodically reconcile" model with **write-time consistency**: every entity mutation triggers immediate, transactional side effects that maintain cross-entity invariants.

Three architectural changes:

1. **Single Source of Truth with Projections** — The `entities` + `workflow_phases` tables are the sole authority. `.meta.json` is a read-optimized projection written atomically after every DB mutation. Derived fields (kanban_column) are computed from authoritative fields (status, workflow_phase), never set independently.

2. **Workspace-Scoped Queries** — Add a mandatory `workspace_id` column to `entities`. Derive it from the project root at registration time. All query APIs default to current-workspace scope with opt-in cross-workspace access.

3. **Post-Mutation Callbacks** — Inline callbacks in existing engine methods that fire after every entity state change. Callbacks handle: dependency cascading (unblock downstream), kanban derivation, projection writes (.meta.json sync), and completion verification (artifact checks). No new abstraction layer — just additional logic in `complete_phase()`, `transition_phase()`, and `update_entity()`.

### Architecture

```
                    +-----------+
                    |  MCP Tool |  (transition_phase, complete_phase, etc.)
                    +-----+-----+
                          |
                          v
                   +------+------+
                   | Write Model |  (entities + workflow_phases tables)
                   | SINGLE SOT  |  ← all mutations go through here
                   +------+------+
                          |
                    post-mutation callbacks (inline in engine methods)
                          |
          +----------+----+----+----------+
          v               v               v
   +-----------+   +-----------+   +-----------+
   | _cascade  |   | _derive   |   | _verify   |
   | _unblock  |   | _kanban + |   | _artifacts|
   |           |   | _project  |   |           |
   |           |   | _meta_json|   |           |
   +-----------+   +-----------+   +-----------+
```

---

## Requirements

### R1: Single Source of Truth (addresses Gaps 3, 5, 8)

**R1.1: Authoritative Fields**
The following fields are authoritative (set directly):
- `entities.status` — the definitive "is this done?" answer
- `workflow_phases.workflow_phase` — the current active phase
- `workflow_phases.last_completed_phase` — highest completed phase

**R1.2: Derived Fields**
The following fields are computed, never set independently:
- `workflow_phases.kanban_column` — derived from `(status, workflow_phase)` using the existing `FEATURE_PHASE_TO_KANBAN` mapping, extended with `status=completed → kanban_column=completed`, `status=abandoned → kanban_column=completed`
- `.meta.json` — projected atomically from DB state after every mutation

**R1.3: Kanban Derivation Rule**
```python
def derive_kanban(status: str, workflow_phase: str | None) -> str:
    if status in ("completed", "abandoned"):
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "planned":
        return "backlog"
    # status == "active" — use phase mapping
    return FEATURE_PHASE_TO_KANBAN.get(workflow_phase, "backlog")
```

**R1.4: .meta.json Projection**
After every DB mutation that changes entity or workflow state, write `.meta.json` from DB state (not the reverse). The `.meta.json` file becomes a cache/projection, not a source of truth. This inverts the current reconciliation direction.

**Pre-inversion migration (critical):**
Before inverting the direction, a one-time migration must:
1. Inventory all fields currently present in `.meta.json` files across all workspaces
2. Ensure every field found is representable in the DB schema (store ad-hoc fields in `entities.metadata` JSON)
3. Run a full `.meta.json → DB` import to populate the DB with all existing data
4. Only then switch the write direction to DB → filesystem

**Degradation path:** If a DB write fails, fall back to direct `.meta.json` write (preserving the existing `_write_meta_json_fallback` path in `engine.py`). Mark the entity for re-sync on next session start. The fallback ensures no data loss when DB is unavailable.

**Rollback strategy:** Before switching write direction, backup all `.meta.json` files via `git stash` or a timestamped copy. If rollback is needed, restore from backup and re-enable the old `.meta.json → DB` reconciliation direction.

**R1.5: Remove Frontmatter Health Check**
Remove frontmatter drift detection from `reconcile_status` until the write pipeline supports frontmatter injection. This restores trust in the health check output.

**Success criteria:** `reconcile_status` reports healthy when all authoritative fields are consistent. Kanban column can never diverge from status + phase because it's never set independently. `.meta.json` always reflects DB state.

---

### R2: Workspace-Scoped Queries (addresses Gaps 1, 10)

**R2.1: Workspace ID Column**
Add `workspace_id TEXT NOT NULL` to the `entities` table. Value is derived at entity registration time using a stable project identifier:

1. **Primary:** Git remote URL — `git remote get-url origin` (stable across clones on different machines/paths)
2. **Fallback:** Canonical path of project root via `realpath` (for repos without remotes)
3. **Override:** `workspace_id` field in `.claude/pd.local.md` (explicit user control)

Resolution order: override > git remote > realpath. This prevents workspace fragmentation when the same repo is cloned to different paths or accessed via symlinks.

**Trade-off acknowledged:** Git remote URL changes when forking or switching remotes. The `pd.local.md` override provides an escape hatch. A `reconcile_workspace --merge <old_id> <new_id>` tool consolidates workspace_ids when this happens.

**R2.2: Default Scoping**
All query APIs (`search_entities`, `export_entities`, `list_features_by_status`, `list_features_by_phase`, `reconcile_check`) default to filtering by `workspace_id = current_workspace` where `current_workspace` is derived from the session's `PROJECT_ROOT`.

**R2.3: Cross-Workspace Opt-In**
All query APIs accept an optional `workspace_id` parameter:
- `workspace_id=None` (default) → current workspace only
- `workspace_id="*"` or `workspace_id="all"` → all workspaces (explicit cross-project queries)
- `workspace_id="<specific path>"` → query a specific workspace

**R2.4: Memory Search Scoping**
`search_memory` adds an optional `project_scope` parameter:
- `project_scope="current"` (default) → filter by current project's `source_project`
- `project_scope="all"` → no filter (current behavior)

**R2.5: Migration**
Existing entities get `workspace_id` populated via the following algorithm:
1. If `artifact_path` is non-null, extract the project root by removing the `/{artifacts_root}/` suffix and everything after it (e.g., `/Users/terry/projects/cast-below/docs/features/001-foo/.meta.json` → `/Users/terry/projects/cast-below`). Then resolve the stable ID (git remote URL if `.git/` exists at that path, else the path itself).
2. If `artifact_path` is null, set `workspace_id = "_unknown"` and log a warning.

A `reconcile_workspace --merge` tool is provided for manual consolidation of `_unknown` entries.

**Success criteria:** `export_entities` from cast-below returns only cast-below entities. Ghost entities from other workspaces are invisible by default.

---

### R3: Post-Mutation Side Effects (addresses Gaps 4, 6, 11, 12)

Rather than a formal reactor bus (which would be overengineered for 4 inline functions), add **post-mutation callbacks** directly in the existing `complete_phase()`, `update_entity()`, and `transition_phase()` methods. This is the simplest approach that achieves the same consistency guarantees — the engine already does this partially (`complete_phase` already calls `update_entity(status='completed')` on finish).

**R3.1: Dependency Data Model (prerequisite for cascading)**
The `blocked_by` concept referenced in Gap 4 does not currently exist in the codebase schema. Add it as a structured metadata convention:

- Store `blocked_by` as a JSON array in `entities.metadata`: `{"blocked_by": ["feature:005-auth", "project:P001"]}`
- `init_feature_state()` accepts an optional `blocked_by` parameter, stored in metadata
- When `blocked_by` is non-empty AND feature has no other blockers (manual status override), set `status = "blocked"`
- `update_feature_metadata` MCP tool (R4.3) can modify `blocked_by`

**R3.2: Post-Mutation Callbacks**

| Callback | Trigger Point | Action |
|----------|--------------|--------|
| `_cascade_unblock` | `complete_phase(phase="finish")`, after setting status=completed | Query `entities.metadata` for all entities in current workspace where metadata JSON contains the completed entity's `type_id` in `blocked_by` array. Remove resolved reference. If `blocked_by` now empty AND status=`blocked`, update status to `planned`. |
| `_derive_and_set_kanban` | Every `update_workflow_phase()` and `update_entity(status=...)` call | Recompute `kanban_column` from `derive_kanban(status, workflow_phase)`. Called inline, not as a separate event. |
| `_project_meta_json` | After every DB mutation in `complete_phase()`, `transition_phase()`, `update_entity()` | Write `.meta.json` from DB state. Runs **after DB transaction commits** (not inside transaction — filesystem writes cannot be rolled back with SQLite). If write fails, log warning and mark entity for re-sync on next session start. |
| `_verify_artifacts` | `complete_phase(phase="finish")`, after status update | Check expected artifacts exist per mode (R4.4 matrix). Log warnings for missing artifacts. Do NOT block completion. |

**R3.3: Session-Start Reconciliation Reporting**
Move session-start reporting out of the callback pattern (it's not a mutation event). Instead, update the reconciliation orchestrator to return a summary dict and surface it in the session-start hook output:
```
"Reconciled: 3 features synced, 1 kanban fixed, 0 warnings"
```
Silent execution only when zero changes are made.

**R3.4: Audit Log**
Post-mutation callbacks log to `~/.claude/pd/reactor.log` as JSONL with timestamp, entity_type_id, callback name, and outcome.

**Success criteria:** Completing a project automatically unblocks downstream features. Kanban column updates atomically with status. Completion logs which artifacts were present/missing. Session-start reconciliation reports what it did.

---

### R4: Operational Flexibility (addresses Gaps 2, 7, 9)

**R4.1: Field Validation on Creation**
`init_feature_state()` rejects empty or null values for `id`, `slug`, and `branch` with `ValueError`. These are identity fields, not optional metadata.

```python
for field, value in [("id", feature_id), ("slug", slug), ("branch", branch)]:
    if not value or not value.strip():
        raise ValueError(f"Feature {field} cannot be empty")
```

**R4.2: Workflow Templates (Phase Sequences)**
Replace the hardcoded `PHASE_SEQUENCE` with mode-specific sequences loaded from a template registry:

```python
WORKFLOW_TEMPLATES = {
    "standard": ["brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish"],
    "bugfix": ["specify", "create-tasks", "implement", "finish"],
    "docs": ["specify", "create-tasks", "implement", "finish"],
    "hotfix": ["implement", "finish"],
    "full": ["brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish"],
}
```

Mode is set at feature creation time and determines the valid phase sequence. Transition validation uses the mode's template instead of the global `PHASE_SEQUENCE`.

**Schema migration:** The `workflow_phases.mode` CHECK constraint (currently `IN ('standard', 'full')`) must be expanded to include `'bugfix'`, `'docs'`, `'hotfix'` via a table rebuild migration (same pattern as migration 5 in `database.py`).

**Interaction with skippedPhases:** `skippedPhases` is retained for backward compatibility but made unnecessary for new features. Templates define the canonical phase sequence; `skippedPhases` provides ad-hoc overrides within a template. Precedence: if a phase is not in the template, it cannot be entered (template is authoritative). If a phase IS in the template, `skippedPhases` can skip it.

**Existing features:** Features created before templates default to `mode=standard` with the full sequence. No migration needed — existing features continue to work unchanged.

**R4.3: Maintenance Mode for meta-json-guard**
Add a `MAINTENANCE_MODE` check to meta-json-guard:

```bash
# Allow maintenance operations
if [[ "${PD_MAINTENANCE:-}" == "1" ]]; then
    output_json "allow" "Maintenance mode active"
    exit 0
fi
```

Also expand MCP tools with `update_feature_metadata(type_id, fields={...})` that allows setting any `.meta.json` field through the sanctioned path.

**R4.4: Artifact Completeness Matrix**
Define expected artifacts per mode:

| Mode | Expected at finish (warn if missing) |
|------|--------------------------------------|
| standard | spec.md, tasks.md, retro.md |
| bugfix | spec.md, tasks.md |
| docs | spec.md, tasks.md |
| hotfix | (none) |
| full | spec.md, design.md, plan.md, tasks.md, retro.md |

The `_verify_artifacts` callback uses this matrix. Warns but does not block.

**Success criteria:** Empty identity fields rejected at creation. Bug fixes skip unnecessary phases. meta-json-guard allows maintenance operations through sanctioned paths. Completion logs artifact presence.

---

## Migration Strategy

### Phase 1: Schema Migration (non-breaking)
1. Add `workspace_id TEXT NOT NULL DEFAULT '_unknown'` to `entities` table (NOT NULL is satisfied by default — no constraint tightening step needed)
2. Backfill `workspace_id` from `artifact_path` using R2.5 algorithm (git remote URL > realpath)
3. Expand `workflow_phases.mode` CHECK constraint to include `'bugfix'`, `'docs'`, `'hotfix'` (table rebuild migration, same pattern as migration 5)
4. Remove frontmatter check from `reconcile_status`

### Phase 2: Single Source of Truth
1. Implement `derive_kanban()` function
2. Replace all direct `kanban_column` sets with `derive_kanban()` calls
3. Add field validation to `init_feature_state()`
4. One-time `.meta.json → DB` full import (inventory all fields, store ad-hoc fields in metadata JSON)
5. Reverse `.meta.json` reconciliation direction (DB → filesystem) — only after step 4 confirms DB has all data
6. Retain `_write_meta_json_fallback` for DB-unavailable degradation

### Phase 3: Post-Mutation Callbacks
1. Implement `_derive_and_set_kanban` inline callback in `update_workflow_phase()` and `update_entity()`
2. Implement `_project_meta_json` post-commit callback
3. Implement `_cascade_unblock` in `complete_phase(phase="finish")`
4. Implement `_verify_artifacts` in `complete_phase(phase="finish")`
5. Update session-start reconciliation orchestrator to return and surface summary

### Phase 4: Operational Flexibility
1. Implement workflow templates registry
2. Update transition validation to use mode-specific sequences
3. Add maintenance mode to meta-json-guard
4. Add `update_feature_metadata` MCP tool

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| DB→filesystem projection breaks existing .meta.json consumers | Medium | High | Full .meta.json→DB import before inversion (Phase 2 step 4). Retain fallback write path. Backup via git stash before switchover. |
| Reactor bus adds write latency | Low | Medium | All reactors are in-process Python, no I/O except .meta.json write (already happening). Budget: <50ms per mutation |
| workspace_id backfill can't resolve paths for deleted projects | Medium | Low | Sentinel value `_unknown` + manual cleanup via `reconcile_prune` |
| Workflow templates break existing features mid-flight | Low | High | Existing features keep `mode=standard` with full sequence. Templates only affect new features |
| Schema migration on shared global DB affects all workspaces | Medium | Medium | Migration is additive (new column with default). No data is removed. Rollback: drop column |

---

## Out of Scope

- Full event sourcing (append-only event log with replay) — overkill for CLI tool with bounded history
- Per-workspace SQLite files — simpler isolation but breaks cross-project lineage queries and complicates migration tooling
- Real-time notifications or WebSocket updates — CLI tool, single user
- Undo/rollback of state transitions — separate feature if needed
- Changes to the agent ecosystem or skill architecture — this PRD focuses on data consistency only

---

## Success Metrics

Reframed as verifiable test assertions:

1. After running `reconcile_status` on a clean workspace, assert `healthy: true` with zero drift entries
2. After registering entities from workspace A, call `export_entities()` from workspace B with default scope — assert zero results from workspace A
3. After calling `complete_phase(phase="finish")` on a project, query all entities where `metadata.blocked_by` contained that project — assert `blocked_by` array no longer contains it and `status` is `planned` (not `blocked`)
4. After any `complete_phase()` or `transition_phase()` call, assert `kanban_column == derive_kanban(status, workflow_phase)`
5. Call `init_feature_state(id="", slug="test", branch="test")` — assert `ValueError` raised
6. Create feature with `mode=bugfix`, call `transition_phase(target="specify")` — assert success. Call `transition_phase(target="design")` — assert rejection (not in bugfix template)
7. Register entity from workspace A, query from workspace B with default scope — assert entity not returned

## Testing Strategy

- All existing test suites (710+ entity registry, 309 workflow engine, 118 reconciliation) must pass after each migration phase
- Migration is tested against a copy of the production DB before applying to the real one
- Post-mutation callbacks are tested using the existing test infrastructure (in-memory DB + temp filesystem)
- Add a migration dry-run mode: `python3 -m migrate_db --dry-run` that reports changes without applying

---

## Appendix: Gap-to-Requirement Traceability

| Gap | Requirement | Mechanism |
|-----|-------------|-----------|
| Gap 1: No cross-project isolation | R2.1, R2.2 | workspace_id column + default filter |
| Gap 2: No field validation | R4.1 | ValueError on empty identity fields |
| Gap 3: Unidirectional reconciliation | R1.4 | DB→filesystem projection (inverted direction) |
| Gap 4: No cascading updates | R3.1, R3.2 _cascade_unblock | Post-completion callback + blocked_by metadata |
| Gap 5: Permanent frontmatter unhealthy | R1.5 | Remove check until implemented |
| Gap 6: Ghost entity accumulation | R2.2, R3.4 | Workspace scoping prevents cross-project ghosts; audit log enables detection |
| Gap 7: Guard blocks maintenance | R4.3 | Maintenance mode + update_feature_metadata MCP tool |
| Gap 8: Three competing "done" signals | R1.1, R1.2, R1.3 | Authoritative fields + derived kanban |
| Gap 9: Rigid phase sequence | R4.2 | Mode-specific workflow templates |
| Gap 10: No memory project scope | R2.4 | search_memory project_scope parameter |
| Gap 11: No artifact completeness | R3.2 _verify_artifacts | Soft validation callback on finish |
| Gap 12: Silent reconciliation | R3.3 | Session-start reconciliation reporting |
