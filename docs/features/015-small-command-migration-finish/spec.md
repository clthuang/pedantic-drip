# Specification: Small Command Migration — finish-feature, show-status, list-features

## Overview

Migrate three "small" commands (`finish-feature`, `show-status`, `list-features`) from inline `.meta.json` parsing and artifact-based phase detection to the workflow state engine MCP tools. These commands are markdown files interpreted by Claude — migration means changing the instructions that tell Claude how to determine phase state and update completion status.

**Key difference from feature 014 (hook migration):** Feature 014 migrated a bash hook using direct Python library imports. Feature 015 migrates command files (markdown prompts) that use MCP tool calls (`get_phase`, `complete_phase`) available to Claude at runtime. The fallback mechanism is Claude checking MCP tool results and falling back to Read/Glob/Edit tools on failure, rather than Python try/except blocks.

**Scope boundary:** Feature 015 covers the three small commands only. The `workflow-transitions` shared skill (used by all phase commands) and the large commands (specify, design, create-plan, create-tasks, implement) are feature 016 scope. Feature discovery (filesystem scanning for active features) is retained — the DB may not contain all features.

**No PRD:** This feature was created without a PRD as it is a mechanical migration of existing behavior to use the workflow state engine.

## Functional Requirements

### FR-1: Replace artifact-based phase detection in `show-status` with `get_phase` MCP

`show-status.md` currently determines phase by checking which artifacts exist:

**Current behavior (Section 1, line 19):**
> determine current phase (first missing artifact from: spec.md, design.md, plan.md, tasks.md — or "implement" if all exist)

This artifact-based detection appears in three sections:
- **Section 1** (Current Context): Phase for the current feature branch
- **Section 1.5** (Project Features): Phase annotation for each project-linked feature
- **Section 2** (Open Features): Phase column for each open feature

**Target behavior:** For each feature where phase is needed:
1. Construct `feature_type_id` as `"feature:{folder_name}"` where `{folder_name}` is the feature directory name (e.g., `015-small-command-migration-finish`). This matches the convention used by entity registry registration.
2. **Skip MCP for non-active features:** Features with `status` of `"completed"`, `"abandoned"`, or `"planned"` should NOT call `get_phase`. Display their status directly from `.meta.json` in the Phase column (e.g., `"completed"`, `"abandoned"`, `"planned"`). Only call `get_phase` for features with `status: "active"`. This applies across all sections: Section 1.5 (project features showing all statuses), Section 2 (open features which may include abandoned), and list-features output.
3. Call `get_phase` MCP tool with that `feature_type_id`.
4. If MCP returns a valid response (no `error` field): use the `current_phase` value from the response. Handle special values:
   - If `current_phase` is `null` (no phase started): display `"specify"` — this is the first actionable phase. The brainstorm phase is pre-feature-creation and is not displayed in status views (brainstorm mode runs before `/iflow:create-feature`, so active features never have `current_phase: "brainstorm"`).
   - If `current_phase` is `"brainstorm"`: display `"specify"` — brainstorm is the initial hydration state for active features with no completed phases (engine returns `PHASE_SEQUENCE[0].value = "brainstorm"`) but is not a user-actionable phase in status views.
   - **Note:** In practice, active features typically return `current_phase="brainstorm"` (hydrated from `.meta.json` with no completed phases). The `null` case is a defensive fallback for DB rows with `NULL` workflow_phase. Both display identically as `"specify"`.
   - If `current_phase` is `"finish"`: display `"finish"` — this is a deliberate improvement over artifact-based detection, which could not distinguish "all artifacts present" from "finish phase active". Artifact-based detection would show `"implement"` in this case.
   - All other values (`"specify"`, `"design"`, `"create-plan"`, `"create-tasks"`, `"implement"`): display as-is.
5. If MCP returns an error or the tool is unavailable: fall back to the current artifact-based detection (first missing artifact from spec.md, design.md, plan.md, tasks.md — or "implement" if all exist).

**Output behavior:** When MCP is available, output is authoritative and may differ from artifact-based detection in edge cases (e.g., `"finish"` phase is distinguishable). When MCP is unavailable, output matches the current artifact-based behavior exactly. This is a deliberate improvement, not a regression — the MCP path provides more accurate phase information.

**Batching consideration:** show-status may query phase for multiple features (all project features + open features). Each requires a separate `get_phase` call. If the first `get_phase` call fails (MCP unavailable), skip MCP for all subsequent features in that invocation and use artifact-based detection for all — avoid repeated failure overhead.

### FR-2: Replace artifact-based phase detection in `list-features` with `get_phase` MCP

`list-features.md` currently determines phase from artifacts and metadata:

**Current behavior (line 17-22):**
> Determine status from artifacts and metadata

**Target behavior:** Same algorithm as FR-1:
1. Construct `feature_type_id` as `"feature:{folder_name}"` from the feature directory name.
2. Skip MCP for non-active features (same rules as FR-1 step 2).
3. Call `get_phase` MCP tool.
4. Use `current_phase` from response, with same special value handling as FR-1 step 4.
5. On error: fall back to artifact-based detection.

**Batching consideration:** Same as FR-1 — if first MCP call fails, skip MCP for remaining features.

**Planned features:** Features with `status: "planned"` have no workflow state in the engine. For these, display phase as `"planned"` directly from `.meta.json` status without calling `get_phase`. This preserves the current behavior (line 23: "or `planned` if status is planned").

### FR-3: Add `complete_phase` MCP call in `finish-feature` Step 6a

`finish-feature.md` Step 6a currently updates `.meta.json` inline with completion state:

**Current behavior (lines 417-428):**
```json
{
  "status": "completed",
  "completed": "{ISO timestamp}",
  "lastCompletedPhase": "finish",
  "phases": {
    "finish": {
      "status": "completed",
      "completed": "{ISO timestamp}"
    }
  }
}
```

**Target behavior — dual-write pattern:**
1. **Keep the existing `.meta.json` update** — `.meta.json` remains the source of truth per project convention.
2. **Add a `complete_phase` MCP call** after the `.meta.json` update:
   - Construct `feature_type_id` as `"feature:{folder_name}"` from the feature directory name.
   - Call `complete_phase(feature_type_id, "finish")`.
   - If MCP succeeds: log success silently (no user-visible output change).
   - If MCP fails for any reason: warn in output but do NOT block completion. The `.meta.json` update already succeeded, so the feature is completed regardless. The DB will be synced later via reconciliation tools (`reconcile_apply`).

**`complete_phase` failure modes:** The MCP call may fail with:
- **MCP unavailable:** Server not running or connection error. Handled by fallback.
- **Phase mismatch:** DB state is behind `.meta.json` (e.g., `current_phase` in DB is not `"finish"`). The engine raises `ValueError` when the requested phase does not match `current_phase` and is not a valid backward re-run. This is expected for features where reconciliation has not run. Handled identically to MCP unavailability — warn, do not block.
- **Feature not found:** Feature entity not registered in DB. Same handling — warn, do not block.

**Rationale for dual-write:** `.meta.json` is the source of truth (confirmed by CLAUDE.md: "prefer updating .meta.json directly (source of truth)"). The `complete_phase` MCP call ensures the DB stays in sync. If MCP is unavailable, the reconciliation tools (`reconcile_apply`) can sync later.

### FR-4: Preserve all existing controls and output formats

All existing behavior must be preserved:
- **show-status:** Section structure, column alignment, footer logic, branch display
- **list-features:** Table format, column headers, commands section, "No active features" message
- **finish-feature:** All steps (1-6) retain identical behavior. Only Step 6a gains the additional MCP call.

### FR-5: Feature discovery remains filesystem-based

Feature discovery (scanning `{iflow_artifacts_root}/features/` for `.meta.json` files) stays as-is in all three commands. The DB may not contain all features (especially older/unregistered ones). MCP tools are used only for phase detection and completion state updates, not for feature enumeration.

## Non-Functional Requirements

### NFR-1: No new dependencies

All MCP tools (`get_phase`, `complete_phase`) are already provided by the workflow-engine MCP server (feature 009). No new servers, tools, or packages are required.

### NFR-2: MCP failure detection pattern

Commands must detect MCP failures consistently. The pattern for all MCP tool calls:
1. Call the MCP tool.
2. Parse the JSON response.
3. Check for `"error": true` in the response — this indicates a structured error from the workflow-engine server.
4. If the tool call itself fails (tool not available, timeout, connection error): the MCP framework surfaces this as a tool error to Claude.
5. In either failure case: fall back to the current inline behavior.

This pattern applies to both read operations (FR-1, FR-2) and write operations (FR-3).

### NFR-3: Phase resolution summary

For clarity, the phase resolution logic across all commands:

| Feature Status | Command | Phase Source | Display Value |
|---|---|---|---|
| `"active"` | show-status, list-features | `get_phase` MCP (fallback: artifact-based) | `current_phase` from MCP response (with special value handling) |
| `"planned"` | show-status, list-features | `.meta.json` status directly | `"planned"` |
| `"completed"` | show-status Section 1.5 | `.meta.json` status directly | `"completed"` |
| `"abandoned"` | show-status Section 1.5, Section 2 | `.meta.json` status directly | `"abandoned"` |

**Note:** Section 2 ("Open Features") currently includes abandoned features (status != "completed" and no project_id). The skip-MCP rule ensures abandoned features display their status from `.meta.json` rather than calling `get_phase`. This preserves existing behavior.

### NFR-4: Output behavior

When MCP is available, commands use MCP state (authoritative). When MCP is unavailable, commands fall back to artifact-based detection (best-effort approximation). In most cases these agree; if they diverge, the MCP-available behavior is considered correct. Users may observe phase differences if the DB and filesystem are out of sync — this is intentional (MCP shows the engine's authoritative view). The only deliberate difference is the `"finish"` phase: MCP can distinguish it, while artifact-based detection shows `"implement"` when all artifacts exist.

## Acceptance Criteria

- AC-1: GIVEN an active feature visible in show-status, WHEN the `get_phase` MCP tool is available, THEN show-status uses `get_phase` for phase detection in Sections 1, 1.5, and 2 instead of artifact-based detection
- AC-2: GIVEN an active feature in list-features output, WHEN the `get_phase` MCP tool is available, THEN list-features uses `get_phase` for phase detection instead of artifact-based detection
- AC-3: GIVEN finish-feature is completing Step 6a, WHEN `.meta.json` has been updated, THEN `complete_phase(feature_type_id, "finish")` is called with `feature_type_id` in format `"feature:{folder_name}"` (e.g., `"feature:015-small-command-migration-finish"`)
- AC-4: GIVEN the `get_phase` MCP tool is unavailable, WHEN show-status or list-features runs, THEN artifact-based phase detection is used and output matches current behavior
- AC-5: GIVEN the `complete_phase` MCP tool fails (unavailable, phase mismatch, or feature not found), WHEN finish-feature completes Step 6a, THEN the feature still completes normally (`.meta.json` update succeeded) with a non-blocking warning
- AC-6: GIVEN a feature with `status: "planned"`, WHEN show-status or list-features runs, THEN phase is displayed as `"planned"` directly from `.meta.json` without calling `get_phase`
- AC-7: GIVEN a feature with `status: "completed"` or `"abandoned"`, WHEN show-status Section 1.5 lists it, THEN the status is displayed from `.meta.json` without calling `get_phase`
- AC-8: GIVEN show-status is scanning 3+ features, WHEN the first `get_phase` call returns an error, THEN the remaining features use artifact-based phase detection AND no additional `get_phase` MCP calls are made in that invocation
- AC-9: GIVEN list-features is scanning 3+ features, WHEN the first `get_phase` call returns an error, THEN the remaining features use artifact-based phase detection AND no additional `get_phase` MCP calls are made in that invocation
- AC-10: GIVEN `get_phase` returns `current_phase` of `null` or `"brainstorm"` for an active feature, WHEN show-status or list-features displays phase, THEN the displayed value is `"specify"`

## Out of Scope

- Migrating `workflow-transitions` shared skill (`validateAndSetup`, `commitAndComplete`) — feature 016
- Migrating large commands (specify, design, create-plan, create-tasks, implement) — feature 016
- Replacing filesystem-based feature discovery with `list_features_by_status` MCP — DB completeness not guaranteed
- Entity registry status updates during finish-feature — handled separately by entity registry MCP
- Adding new tests — command files are markdown instructions, not executable code

## Verification Strategy

Verification is manual — command files are markdown instructions, not executable code:
1. Run `/iflow:show-status` with the workflow-engine MCP server running and confirm phase output uses `get_phase` values.
2. Stop the workflow-engine MCP server and re-run `/iflow:show-status` to confirm artifact-based fallback produces identical output.
3. Run `/iflow:finish-feature` on a test feature and confirm `complete_phase` is called after `.meta.json` update.
4. Run `/iflow:finish-feature` with the MCP server stopped and confirm completion succeeds with a non-blocking warning.

To confirm MCP usage, check the tool call history in the Claude session — `get_phase` calls will appear in the tool invocation log. Alternatively, test with a feature where the DB state differs from artifacts (e.g., DB shows `"finish"` but all artifacts exist — artifact-based would show `"implement"`, MCP would show `"finish"`).

## Technical Notes

- `get_phase` returns `FeatureWorkflowState` serialized as: `{feature_type_id, current_phase, last_completed_phase, completed_phases, mode, source, degraded}`. The `current_phase` field is the replacement for artifact-based detection. The `source` field indicates the state origin: `"db"` (from database), `"meta_json"` (hydrated from `.meta.json` into DB), or `"meta_json_fallback"` (DB unavailable, read directly from `.meta.json`).
- `complete_phase` returns the updated `FeatureWorkflowState` after marking the phase as completed. In the normal (DB-available) path, it writes to the DB only and does NOT write to `.meta.json` — hence the dual-write pattern in FR-3. In degraded mode (DB unavailable), it falls back to `.meta.json` writes, but this is irrelevant for FR-3 since the command updates `.meta.json` first.
- The `degraded` field in `get_phase` response is `true` when `source == "meta_json_fallback"`. This is informational and does not affect command behavior.
- MCP tool calls from commands use the standard Claude MCP tool invocation syntax. No PYTHONPATH or subprocess management is needed (unlike hook migration in feature 014).
