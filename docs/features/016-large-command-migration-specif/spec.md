# Specification: Large Command Migration — specify, design, create-plan, create-tasks, implement + workflow-transitions

## Overview

Migrate the five large phase commands (`specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`, `implement.md`) and the shared `workflow-transitions` skill to use the workflow state engine MCP tools for phase transitions and completion state. This is the dual-write migration pattern established by feature 015 — `.meta.json` remains the source of truth, MCP calls are best-effort secondary writes for DB synchronization.

**Key difference from feature 015 (small command migration):** Feature 015 migrated read-only phase detection (`get_phase`) and a single completion write (`complete_phase` in finish-feature). Feature 016 migrates the **write-heavy shared infrastructure** — `validateAndSetup()` (phase start transitions) and `commitAndComplete()` (phase completion marking) — which are invoked by all five large commands via the `workflow-transitions` skill.

**Scope boundary:** Feature 016 covers:
1. `workflow-transitions/SKILL.md` — add `transition_phase` and `complete_phase` MCP calls
2. The five large command files — no direct changes needed (they delegate to the skill)

Feature 016 does NOT cover:
- The three small commands already migrated in feature 015 (show-status, list-features, finish-feature)
- Domain-specific `.meta.json` metadata (reviewer notes, stage tracking, task concerns) — these are not workflow phase state
- Replacing filesystem-based feature discovery
- Modifying the state engine itself

**No PRD:** This feature was created as part of the P001 project decomposition. The project PRD provides the overarching context.

**PRD traceability:** PRD FR-12 ("all commands use MCP calls instead of inline .meta.json manipulation") is delivered incrementally: feature 016 adds MCP calls alongside `.meta.json` writes (dual-write); feature 017 removes `.meta.json` writes (cutover). FR-12 is fully satisfied only after feature 017.

## Functional Requirements

### FR-1: Add `transition_phase` MCP call to `validateAndSetup()` Step 4

`workflow-transitions/SKILL.md` Step 4 (Mark Phase Started) currently writes directly to `.meta.json`:

**Current behavior (Step 4: Mark Phase Started):**
```json
{
  "phases": {
    "{phaseName}": {
      "started": "{ISO timestamp}"
    }
  }
}
```

**Target behavior — dual-write pattern:**
1. **Keep the existing `.meta.json` update** — `.meta.json` remains the source of truth.
2. **Add a `transition_phase` MCP call** after the `.meta.json` update:
   - Construct `feature_type_id` as `"feature:{id}-{slug}"` from the feature's `.meta.json` `id` and `slug` fields. This matches the convention used by entity registry registration and feature 015's `feature_type_id` construction.
   - Call `transition_phase(feature_type_id, "{phaseName}")`.
   - If MCP succeeds: log success silently (no user-visible output change).
   - If MCP fails for any reason: warn using the standard format (see NFR-3) but do NOT block. The `.meta.json` update already succeeded, so the phase has started regardless. The DB will sync later via reconciliation.

**Interaction with YOLO mode:** The `yolo_active` parameter of `transition_phase` should be set to `true` when `[YOLO_MODE]` is active in the execution context. When `[YOLO_MODE]` is NOT active, omit the `yolo_active` parameter (defaults to `false`) or explicitly pass `yolo_active=false`. This allows the engine to record YOLO mode for audit purposes.

**`transition_phase` failure modes:**
- **MCP unavailable:** Server not running or connection error. Handled by fallback.
- **Transition rejected:** Engine determines the transition is invalid (e.g., prerequisites not met). This is informational — the command has already validated via its own logic. Warn, do not block.
- **Feature not found:** Entity not registered in DB. Warn, do not block.

### FR-2: Add `complete_phase` MCP call to `commitAndComplete()` Step 2

`workflow-transitions/SKILL.md` Step 2 (Update State) currently writes directly to `.meta.json`:

**Current behavior (commitAndComplete Step 2: Update State):**
```json
{
  "phases": {
    "{phaseName}": {
      "completed": "{ISO timestamp}",
      "iterations": {count},
      "reviewerNotes": ["any unresolved concerns"]
    }
  },
  "lastCompletedPhase": "{phaseName}"
}
```

**Target behavior — dual-write pattern:**
1. **Keep the existing `.meta.json` update** — `.meta.json` remains the source of truth.
2. **Add a `complete_phase` MCP call** after the `.meta.json` update:
   - Use the same `feature_type_id` constructed in `validateAndSetup()` (or re-construct from `.meta.json` if needed).
   - Call `complete_phase(feature_type_id, "{phaseName}")`.
   - If MCP succeeds: log success silently (no user-visible output change).
   - If MCP fails for any reason: warn using the standard format (see NFR-3) but do NOT block. The `.meta.json` update already succeeded.

**`complete_phase` failure modes:** Same as FR-1 — MCP unavailable, phase mismatch (DB state behind `.meta.json`), feature not found. All handled identically: warn, do not block.

### FR-3: Preserve all existing behavior in the five command files

The five large command files (`specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`, `implement.md`) delegate phase transition management to `workflow-transitions`. Since the migration occurs in the skill, the command files require **no direct changes** for the dual-write MCP integration.

The following inline `.meta.json` operations in commands are **out of scope** — they are domain metadata, not workflow phase state tracked by the engine:

| Command | Inline `.meta.json` Operation | Why Out of Scope |
|---------|------------------------------|------------------|
| specify.md | WRITE `reviewerNotes` (spec-reviewer cap) | Reviewer metadata, not phase state |
| specify.md | WRITE `phaseReview.reviewerNotes` (phase-reviewer cap) | Reviewer metadata |
| design.md | WRITE `stages.research.*`, `stages.architecture.*`, `stages.interface.*`, `stages.designReview.*`, `stages.handoffReview.*` | Design sub-stage tracking, not modeled in engine |
| create-plan.md | WRITE `reviewerNotes`, `phaseReview.reviewerNotes` | Reviewer metadata |
| create-tasks.md | WRITE `taskReview.concerns`, `chainReview.concerns` | Review metadata |
| implement.md | WRITE `reviewerNotes` (circuit breaker force-approve) | Reviewer metadata |
| All | READ `brainstorm_source` for PRD resolution | Artifact path resolution, not state |

### FR-4: `feature_type_id` construction in `workflow-transitions`

The skill currently constructs `entity_type_id` for frontmatter injection (Step 1, line 164):
> Construct `entity_type_id` as `"feature:{id}-{slug}"` from `.meta.json`.

The same `feature_type_id` format must be used for `transition_phase` and `complete_phase` MCP calls. The skill already reads `.meta.json` to get `id` and `slug`, so no additional file reads are needed.

**Consistency requirement:** The `feature_type_id` format MUST be `"feature:{id}-{slug}"` — matching the entity registry convention and feature 015's established pattern. Example: `"feature:016-large-command-migration-specif"`.

**Terminology note:** Feature 015 uses `{folder_name}` and the existing skill uses `entity_type_id` — these all resolve to the same value: the feature directory name, which follows the `{id}-{slug}` pattern. This spec standardizes on `feature_type_id` for MCP call parameters.

## Non-Functional Requirements

### NFR-1: No new dependencies

All MCP tools (`transition_phase`, `complete_phase`) are already provided by the workflow-engine MCP server (feature 009). No new servers, tools, or packages are required.

### NFR-2: MCP failure detection pattern

The failure detection pattern from feature 015 applies:
1. Call the MCP tool.
2. Parse the JSON response.
3. Check for `"error": true` in the response — structured error from the workflow-engine server.
4. If the tool call itself fails (tool not available, timeout, connection error): the MCP framework surfaces this as a tool error to Claude.
5. In either failure case: warn and continue (do not block).

### NFR-3: Warning format

On MCP failure, use the standard warning format established by feature 015:

```
Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.
```

Where `{reason}` is a brief description of the failure (e.g., "MCP tool unavailable", "transition rejected", "feature not found").

### NFR-4: Migration scope is minimal — skill only

The migration touches exactly one file: `plugins/iflow/skills/workflow-transitions/SKILL.md`. The five command files require no changes because they delegate all phase state management to this skill.

This is intentional — the skill encapsulates the shared boilerplate, and the migration leverages that encapsulation. Changing the skill automatically affects all five commands. However, verification requires testing all five phase commands end-to-end since they all consume this skill.

### NFR-5: Dual-write ordering

The ordering is always:
1. `.meta.json` write (primary, source of truth) — FIRST
2. MCP tool call (secondary, DB sync) — SECOND

If the `.meta.json` write fails, skip the MCP call (the phase operation failed). If the `.meta.json` write succeeds but the MCP call fails, the phase operation is still considered successful.

## Acceptance Criteria

- AC-1: GIVEN `validateAndSetup("specify")` is called, WHEN `.meta.json` is updated with `phases.specify.started`, THEN `transition_phase(feature_type_id, "specify")` is called with `feature_type_id` in format `"feature:{id}-{slug}"`
- AC-2: GIVEN `commitAndComplete("specify", ["spec.md"])` is called, WHEN `.meta.json` is updated with `phases.specify.completed` and `lastCompletedPhase`, THEN `complete_phase(feature_type_id, "specify")` is called
- AC-3: GIVEN `transition_phase` MCP call fails (unavailable, rejected, or feature not found), WHEN `validateAndSetup()` is executing, THEN the phase still starts normally (`.meta.json` update succeeded) with a non-blocking warning
- AC-4: GIVEN `complete_phase` MCP call fails, WHEN `commitAndComplete()` is executing, THEN the phase still completes normally (`.meta.json` update succeeded) with a non-blocking warning
- AC-5: GIVEN YOLO mode is active, WHEN `transition_phase` is called, THEN `yolo_active` parameter is set to `true`
- AC-6: GIVEN any phase command (specify, design, create-plan, create-tasks, implement) runs end-to-end, WHEN the workflow-engine MCP server is available, THEN `transition_phase` is called in `validateAndSetup()` Step 4 (after `.meta.json` started timestamp is written) and `complete_phase` is called in `commitAndComplete()` Step 2 (after `.meta.json` completed timestamp is written)
- AC-7: GIVEN any phase command runs end-to-end, WHEN the workflow-engine MCP server is unavailable, THEN the command completes identically to current behavior (`.meta.json` only) with non-blocking warnings
- AC-8: GIVEN `feature_type_id` is constructed in `workflow-transitions`, WHEN it is used for MCP calls, THEN the format matches `"feature:{id}-{slug}"` consistent with entity registry convention
- AC-9: GIVEN domain metadata writes (reviewer notes, stage tracking, task concerns) occur in commands, WHEN the migration is complete, THEN these writes remain as inline `.meta.json` operations with no MCP involvement
- AC-10: GIVEN `validateAndSetup()` Step 1 already validates transitions via its own logic (reading `.meta.json`), WHEN `transition_phase` returns a rejection, THEN the rejection is logged as a warning but does NOT override the skill's own validation result

## Out of Scope

- Small commands already migrated in feature 015 (show-status, list-features, finish-feature)
- The `create-feature` command — it creates `.meta.json` from scratch, not a phase transition
- Domain-specific `.meta.json` metadata: reviewer notes, design stage tracking, task concerns, brainstorm source reads
- Replacing filesystem-based feature discovery with DB queries
- Modifying the state engine (feature 008/009) or adding new MCP tools
- Reconciliation tooling (feature 011)
- Removing `.meta.json` writes (cutover is feature 017)

## Verification Strategy

Verification is manual — skill and command files are markdown instructions, not executable code:

1. Run `/iflow:specify` on a test feature with the workflow-engine MCP server running and confirm `transition_phase` is called in Step 4 of `validateAndSetup()` and `complete_phase` is called in Step 2 of `commitAndComplete()`.
2. Stop the workflow-engine MCP server and re-run a phase command to confirm the command completes identically with non-blocking warnings.
3. Check the entity DB after a successful run to verify the phase state matches `.meta.json` state.
4. Run a phase command in YOLO mode and verify `yolo_active=true` is passed to `transition_phase`.
5. After a successful phase run, query `get_phase` with the same `feature_type_id` used by `transition_phase`/`complete_phase` and confirm the phase state matches. This validates both the format correctness and round-trip consistency.

## Technical Notes

- `transition_phase` returns `{transitioned: bool, results: [...], degraded: bool}`. The `transitioned` field indicates success. Error responses have the shape `{error: true, error_type: "...", message: "...", recovery_hint: "..."}` — this JSON is produced by the MCP server's error handling decorators (`_with_error_handling`, `_catch_value_error`), not by the engine methods directly. The engine methods raise `ValueError`; the MCP layer converts these to structured JSON errors.
- `complete_phase` returns the updated `FeatureWorkflowState` on success. Error handling follows the same MCP decorator pattern as `transition_phase`.
- The skill's Step 1 (Validate Transition) already validates transitions via its own logic. The `transition_phase` MCP call in Step 4 provides a secondary validation — if the engine rejects, it's logged but not blocking. The two validation paths may disagree if the DB state diverges from `.meta.json` (expected during migration period).
- Design's `stages` sub-object (12+ writes for research, architecture, interface, designReview, handoffReview) represents sub-phase tracking not modeled in `FeatureWorkflowState`. The engine only tracks top-level phases. These stay as inline `.meta.json` writes.
- MCP tool calls from skills use the standard Claude MCP tool invocation syntax. No PYTHONPATH or subprocess management is needed.
