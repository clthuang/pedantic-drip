# Spec: Entity Depth Fixes

Four targeted fixes for entity consistency depth bugs across `entity_registry` and `workflow_engine` reconciliation subsystems.

Origin: These fixes were identified through code inspection of depth-guard inconsistencies. No PRD/brainstorm exists — this is a targeted bug-fix batch.

## Background

The entity registry enforces a depth guard (AC-14) at 10 hops for lineage traversal (`get_lineage`), but this constraint is inconsistently applied across related operations. Several code paths bypass or omit depth checks, creating potential for unbounded queries, inconsistent state, and misleading diagnostics.

## Requirements

### R1: Depth-guard `set_parent()` circular reference check

**Problem:** `database.py:703-716` — the circular reference detection CTE in `set_parent()` has no depth limit. While `_lineage_up()` and `_lineage_down()` both use `WHERE a.depth < ?` with `max_depth=10`, the `set_parent()` CTE recurses without bound. In deeply nested hierarchies, this can cause runaway queries.

**Fix:** Add a `depth` counter column and `WHERE depth < ?` guard to the `set_parent()` ancestor CTE, consistent with `_lineage_up()`. Use the same default max_depth (10). If the depth limit is reached without finding a cycle, allow the operation.

**Known limitation:** Cycles beyond 10 hops from the child node will not be detected. This is accepted because well-formed trees in this system do not exceed 10 levels (enforced by AC-14 in `get_lineage`).

**Acceptance criteria:**
- AC-1.1: `set_parent()` CTE includes `depth < max_depth` guard matching `_lineage_up()` pattern
- AC-1.2: Existing circular reference detection still works for chains ≤10 hops
- AC-1.3: Chains >10 hops do not cause unbounded recursion — operation succeeds (no cycle found within depth limit)
- AC-1.4: New test: 11-hop chain with no cycle → `set_parent()` succeeds without hanging

### R2: `_derive_expected_kanban()` status-awareness

**Problem:** `reconciliation.py:175-190` — `_derive_expected_kanban()` maps `workflow_phase` → kanban column but ignores feature `status`. Features with `status="completed"` or `status="abandoned"` that don't have matching phase state get incorrect kanban derivation. The `_check_single_feature()` function reads `meta.get("status")` into the report but never uses it for kanban logic.

**Fix:** Extend `_derive_expected_kanban()` to accept an optional `status` parameter. When `status == "completed"`, return `"completed"` regardless of phase. When `status == "abandoned"`, return `"abandoned"`. Update callers in `_check_single_feature()` and `_reconcile_single_feature()` to pass status through.

**Acceptance criteria:**
- AC-2.1: `_derive_expected_kanban(workflow_phase="implement", ..., status="completed")` returns `"completed"`
- AC-2.2: `_derive_expected_kanban(workflow_phase="implement", ..., status="abandoned")` returns `"abandoned"`
- AC-2.3: `_derive_expected_kanban(workflow_phase="implement", ..., status="active")` unchanged (existing behavior)
- AC-2.4: Kanban drift detection correctly identifies stale kanban columns for completed/abandoned features
- AC-2.5: Reconciliation updates kanban column for status-terminal features

### R3: Artifact path verification in entity reconciliation

**Problem:** During entity reconciliation and drift detection (`_check_single_feature()` in `reconciliation.py`), artifact paths referenced in entity records are assumed to exist on disk. Deep hierarchies with missing intermediate artifacts can produce orphaned entity records or misleading drift reports.

**Fix:** Add `os.path.exists()` check on entity artifact paths within `_check_single_feature()` before drift comparison. When an artifact path doesn't exist, flag it in the drift report.

**Acceptance criteria:**
- AC-3.1: `WorkflowDriftReport` gains an `artifact_missing: bool = False` field
- AC-3.2: `_check_single_feature()` sets `artifact_missing=True` when the feature's artifact path doesn't exist on disk
- AC-3.3: Missing artifacts don't cause reconciliation to crash or hang
- AC-3.4: `WorkflowDriftResult.summary` dict includes `artifact_missing_count` key

### R4: Depth context in reconciliation reporting

**Problem:** `WorkflowDriftReport` (frozen dataclass at `reconciliation.py:37-45`) doesn't include entity depth or hierarchy context. When diagnosing drift in deeply nested features, the report lacks information about where the entity sits in the hierarchy.

**Fix:** Add optional `depth` and `parent_type_id` fields to `WorkflowDriftReport` with `default=None` so existing call sites and test constructors continue to work without changes. Populate from entity registry DB when available within `_check_single_feature()`. Include in human-readable reconciliation output.

**Acceptance criteria:**
- AC-4.1: `WorkflowDriftReport` includes `depth: int | None = None` field
- AC-4.2: `WorkflowDriftReport` includes `parent_type_id: str | None = None` field
- AC-4.3: Human-readable reconciliation output shows depth context for nested entities (e.g., `"depth: 3, parent: project:001-my-project"`)
- AC-4.4: Fields are None when entity has no parent (root entities)
- AC-4.5: Existing test constructors of `WorkflowDriftReport` compile without changes (default=None)

## Scope Boundaries

**In scope:**
- The four fixes listed above
- Tests for each fix
- Updating existing tests that break due to signature changes

**Out of scope:**
- Changing the max_depth constant (stays at 10)
- Adding configurable depth limits
- Refactoring entity registry architecture
- UI changes to display depth information
- Frontmatter validation changes (reviewed: `validate_header()` is a pure schema validator with no parent/DB lookups)
- Degraded-mode changes (reviewed: degraded mode deals with phase transitions, not entity parent relationships)

## Technical Notes

- Key files: `plugins/pd/hooks/lib/entity_registry/database.py`, `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- Test commands: see CLAUDE.md for entity registry and workflow engine test commands
- All fixes must maintain backward compatibility with existing entity DB schema (no migrations)
- New fields on frozen dataclasses use `default=None` to maintain backward compatibility with existing constructors
