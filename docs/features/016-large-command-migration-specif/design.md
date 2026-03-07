# Design: Large Command Migration — workflow-transitions dual-write

## Prior Art Research

### Codebase Patterns

1. **finish-feature.md Step 6a** — canonical dual-write for `complete_phase` established by feature 015. Constructs `feature_type_id` as `"feature:{folder_name}"`, calls `complete_phase(feature_type_id, "finish")`, warns on failure with standard format, never blocks.

2. **show-status.md / list-features.md** — dual-read for `get_phase` (feature 015). Calls `get_phase(feature_type_id)`, falls back to artifact-based detection. Batching optimization: if first call fails, skip MCP for remaining features.

3. **workflow-transitions SKILL.md** — current structure:
   - `validateAndSetup()` Step 4 writes `phases.{phaseName}.started` to `.meta.json` (lines 106-117) — no MCP call.
   - `commitAndComplete()` Step 2 writes completion state to `.meta.json` (lines 187-201) — no MCP call.
   - Step 1 (line 164) already constructs `entity_type_id` as `"feature:{id}-{slug}"` for frontmatter injection — same format needed for MCP calls.

4. **MCP tool signatures** — `transition_phase(feature_type_id, target_phase, yolo_active=False)` returns `{transitioned, results, degraded}`; `complete_phase(feature_type_id, phase)` returns updated `FeatureWorkflowState`. Error shape: `{error: true, error_type, message, recovery_hint}`.

5. **YOLO mode detection** — SKILL.md checks `[YOLO_MODE]` marker in conversation context (lines 14-26). Same detection applies for setting `yolo_active` parameter.

### External Patterns

- **Dual-write with leader/follower** — `.meta.json` is the leader; DB is the follower. Follower failures are tolerable (reconciliation catches up).
- **Graceful degradation** — warn-and-continue pattern aligns with circuit breaker "open" state where secondary writes are skipped.
- **Write-through caching** — analogous: primary store (`.meta.json`) always written; cache (DB) written best-effort.

## Architecture Overview

### Component: workflow-transitions SKILL.md (single file change)

The migration modifies two procedures in one file:

```
validateAndSetup(phaseName)
  Step 1: Validate Transition        ← unchanged
  Step 2: Check Branch               ← unchanged
  Step 3: Check for Partial Phase    ← unchanged
  Step 4: Mark Phase Started         ← ADD transition_phase MCP call
  Step 5: Inject Project Context     ← unchanged

commitAndComplete(phaseName, artifacts[])
  Step 1: Auto-Commit                ← unchanged
  Step 2: Update State               ← ADD complete_phase MCP call
```

### Change Summary

Two insertions, zero deletions, zero modifications to existing behavior:

1. **validateAndSetup Step 4** — After the existing `.meta.json` update (lines 108-117), add a new sub-step that calls `transition_phase`. The existing `.meta.json` write remains untouched.

2. **commitAndComplete Step 2** — After the existing `.meta.json` update (lines 189-201), add a new sub-step that calls `complete_phase`. The existing `.meta.json` write remains untouched.

### Data Flow

```
Phase Start:
  .meta.json ──write──→ phases.{phaseName}.started     [EXISTING, unchanged]
       │
       ▼
  transition_phase(feature_type_id, phaseName, yolo_active)  [NEW]
       │
       ├─ success → silent, continue
       └─ failure → warn, continue

Phase Complete:
  .meta.json ──write──→ phases.{phaseName}.completed    [EXISTING, unchanged]
                        lastCompletedPhase
       │
       ▼
  complete_phase(feature_type_id, phaseName)             [NEW]
       │
       ├─ success → silent, continue
       └─ failure → warn, continue
```

### feature_type_id Construction

The skill already reads `.meta.json` for `id` and `slug` in `commitAndComplete` Step 1 (frontmatter injection, line 164). The same values produce `feature_type_id`:

```
feature_type_id = "feature:{id}-{slug}"
Example: "feature:016-large-command-migration-specif"
```

No additional file reads needed — `.meta.json` is already parsed by the skill.

## Technical Decisions

### D1: Additive insertion, not inline modification

The MCP call blocks are added as new sub-steps after existing `.meta.json` writes. The existing prose is not modified. This minimizes diff size and preserves the skill's current behavior exactly.

**Rationale:** Reduces review burden. The existing `.meta.json` writes are untouched, so no regression risk to current behavior. The MCP calls are purely additive.

### D2: Reuse existing entity_type_id construction

The skill constructs `entity_type_id` in `commitAndComplete` Step 1 (line 164) for frontmatter injection. The same format is used for MCP calls. In `validateAndSetup`, the skill reads `.meta.json` (Step 1) to validate transitions — `id` and `slug` are available from that read.

**Rationale:** No new file reads, no new variables. Consistent format across all uses.

### D3: Inline MCP prose, not extracted helper

The MCP call + error handling is written inline in each step (approximately 10-15 lines each) rather than extracted into a shared helper section.

**Rationale:** Two call sites is below the threshold for extraction. Inline keeps each step self-contained and readable. The skill is markdown instructions, not executable code — "DRY" applies less strictly.

### D4: YOLO detection for transition_phase only

`yolo_active` parameter only applies to `transition_phase` (the engine records it for audit). `complete_phase` has no `yolo_active` parameter in its API signature.

**Rationale:** Matches the MCP tool API. The engine uses YOLO mode for transition gate auditing, not completion marking.

## Risks

### R1: MCP server unavailability during first deployment (Low)

If the workflow-engine MCP server is not running when a phase command executes, both MCP calls will fail. The warn-and-continue pattern handles this identically to pre-migration behavior.

**Mitigation:** Standard warning format. Reconciliation catches up later.

### R2: DB state diverges from .meta.json (Expected, Low impact)

Until feature 017 (cutover), the DB is a secondary follower. If MCP calls fail intermittently, the DB will lag. This is by design.

**Mitigation:** `reconcile_apply` (feature 011) resolves drift. AC-11 verifies round-trip consistency when both calls succeed.

### R3: Partial-phase resume calls transition_phase for already-active phase (Low)

On partial-phase resume (Step 3 → "Continue"), Step 4 re-runs and calls `transition_phase` for a phase the DB may already show as current (from the original started run). The engine treats same-phase-to-same-phase as a no-op or valid re-entry — either way, the standard warn-and-continue pattern handles any rejection.

**Mitigation:** Engine's transition logic handles re-entry gracefully. If it rejects, the warning is informational and the phase proceeds normally via `.meta.json`.

### R4: Skill-level validation blocks prevent DB signal (Accepted)

If Step 1 (Validate Transition) blocks execution, Step 4 never runs and no `transition_phase` MCP call is made. The DB does not record blocked transitions. This is by design — blocked transitions should not produce DB state changes.

**Mitigation:** None needed. Correct behavior.

### R5: Skill markdown interpretation variance (Low)

Claude interprets the skill instructions. Adding more prose increases the chance of misinterpretation (e.g., calling MCP before `.meta.json` write instead of after).

**Mitigation:** Clear ordering prose ("After the `.meta.json` update above..."), explicit dual-write ordering note, and NFR-5 from spec.

## Interfaces

### Interface 1: transition_phase MCP call (validateAndSetup Step 4)

**Caller:** workflow-transitions skill, Step 4, after `.meta.json` started timestamp write.

**MCP tool:** `transition_phase`

**Parameters:**
| Parameter | Source | Example |
|-----------|--------|---------|
| `feature_type_id` | `"feature:{id}-{slug}"` from `.meta.json` | `"feature:016-large-command-migration-specif"` |
| `target_phase` | `{phaseName}` argument | `"specify"` |
| `yolo_active` | `true` if `[YOLO_MODE]` in context, else omit | `true` |

**Success response:** `{transitioned: true, results: [...], degraded: false}` — no output, continue.

**Error responses:**
- Structured error: `{error: true, error_type: "...", message: "...", recovery_hint: "..."}` — warn with reason from `message`.
- Tool unavailable: MCP framework surfaces tool error — warn with "MCP tool unavailable".
- Transition rejected (`transitioned: false`): — warn with "transition rejected".

**Warning format:** `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`

### Interface 2: complete_phase MCP call (commitAndComplete Step 2)

**Caller:** workflow-transitions skill, Step 2, after `.meta.json` completion state write.

**MCP tool:** `complete_phase`

**Parameters:**
| Parameter | Source | Example |
|-----------|--------|---------|
| `feature_type_id` | `"feature:{id}-{slug}"` from `.meta.json` | `"feature:016-large-command-migration-specif"` |
| `phase` | `{phaseName}` argument | `"specify"` |

**Success response:** Updated `FeatureWorkflowState` — no output, continue.

**Error responses:**
- Structured error: `{error: true, error_type: "invalid_transition" | "feature_not_found" | "db_unavailable", message: "...", recovery_hint: "..."}` — warn with reason from `message`.
- Tool unavailable: MCP framework surfaces tool error — warn with "MCP tool unavailable".

**Warning format:** Same as Interface 1.

### Interface 3: Command files (unchanged)

The five command files (`specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`, `implement.md`) delegate to `workflow-transitions` skill via `validateAndSetup(phaseName)` and `commitAndComplete(phaseName, artifacts[])`. No interface changes — the skill absorbs the MCP integration transparently.

### Prose Template: transition_phase block (for Step 4 insertion)

```markdown
**Sync to workflow DB (best-effort):**

After the `.meta.json` update above, sync the phase transition to the workflow database:

1. Construct `entity_type_id` as `"feature:{id}-{slug}"` from the `.meta.json` `id` and `slug` fields (available from the `.meta.json` read in Step 1).
2. Call `transition_phase(entity_type_id, "{phaseName}")`.
   - If `[YOLO_MODE]` is active in the current context: include `yolo_active=true`.
   - If `[YOLO_MODE]` is NOT active: omit `yolo_active` (defaults to `false`).
3. If the call succeeds (response contains `transitioned: true` and `degraded: false`): no output, proceed to Step 5.
4. If the call fails (MCP tool unavailable, response contains `error: true`, `transitioned: false`, or `degraded: true`):
   output `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`
   where `{reason}` is a brief description (e.g., "MCP tool unavailable", "transition rejected", "feature not found").
   Do NOT block — the `.meta.json` update already succeeded.

Note: On partial-phase resume (Step 3 → "Continue"), this call may target a phase already active in the DB. The engine handles re-entry gracefully; any rejection is covered by step 4's warn-and-continue.
```

### Prose Template: complete_phase block (for Step 2 insertion)

```markdown
**Sync to workflow DB (best-effort):**

After the `.meta.json` update above, sync the phase completion to the workflow database:

1. Construct `entity_type_id` as `"feature:{id}-{slug}"` from `.meta.json` `id` and `slug` fields (same value used in `validateAndSetup` Step 4, and in Step 1 frontmatter injection).
2. Call `complete_phase(entity_type_id, "{phaseName}")`.
3. If the call succeeds: no output, proceed.
4. If the call fails (MCP tool unavailable, response contains `error: true`, or phase mismatch):
   output `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`
   Do NOT block — the `.meta.json` update already succeeded.
```
