# Specification: Small Command Migration — finish-feature, show-status, list-features

## Overview

Migrate three "small" commands (`finish-feature`, `show-status`, `list-features`) from inline `.meta.json` parsing and artifact-based phase detection to the workflow state engine MCP tools. These commands are markdown files interpreted by Claude — migration means changing the instructions that tell Claude how to determine phase state and update completion status.

**Key difference from feature 014 (hook migration):** Feature 014 migrated a bash hook using direct Python library imports. Feature 015 migrates command files (markdown prompts) that use MCP tool calls (`get_phase`, `complete_phase`) available to Claude at runtime. The fallback mechanism is Claude checking MCP tool results and falling back to Read/Glob/Edit tools on failure, rather than Python try/except blocks.

**Scope boundary:** Feature 015 covers the three small commands only. The `workflow-transitions` shared skill (used by all phase commands) and the large commands (specify, design, create-plan, create-tasks, implement) are feature 016 scope. Feature discovery (filesystem scanning for active features) is retained — the DB may not contain all features.

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
1. Construct `feature_type_id` as `"feature:{id}-{slug}"` from `.meta.json` fields already read during feature scanning.
2. Call `get_phase` MCP tool with that `feature_type_id`.
3. If MCP returns a valid response (no `error` field): use the `current_phase` value from the response. If `current_phase` is `null` (no phase started), display `"specify"` (first actionable phase).
4. If MCP returns an error or the tool is unavailable: fall back to the current artifact-based detection (first missing artifact from spec.md, design.md, plan.md, tasks.md — or "implement" if all exist).

**Output preservation:** The phase string displayed must match the current format exactly. The `current_phase` values from `get_phase` use the same strings (`"specify"`, `"design"`, `"create-plan"`, `"create-tasks"`, `"implement"`, `"finish"`) as the artifact-based detection.

**Batching consideration:** show-status may query phase for multiple features (all project features + open features). Each requires a separate `get_phase` call. If the first `get_phase` call fails (MCP unavailable), skip MCP for all subsequent features in that invocation and use artifact-based detection for all — avoid repeated failure overhead.

### FR-2: Replace artifact-based phase detection in `list-features` with `get_phase` MCP

`list-features.md` currently determines phase from artifacts and metadata:

**Current behavior (line 17-22):**
> Determine status from artifacts and metadata

**Target behavior:** Same algorithm as FR-1:
1. Construct `feature_type_id` from `.meta.json`.
2. Call `get_phase` MCP tool.
3. Use `current_phase` from response. If `current_phase` is `null`, display `"specify"`.
4. On error: fall back to artifact-based detection.

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
   - Construct `feature_type_id` as `"feature:{id}-{slug}"`.
   - Call `complete_phase(feature_type_id, "finish")`.
   - If MCP succeeds: log success silently (no user-visible output change).
   - If MCP fails: warn in output but do NOT block completion. The `.meta.json` update already succeeded, so the feature is completed regardless. The DB will be synced later via reconciliation tools.

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

### NFR-3: No behavioral regression

Users must not observe any difference in command output when MCP is available vs unavailable. The MCP tools provide the same data that artifact-based detection and `.meta.json` reads provide — just from a different source. If there is a discrepancy between MCP state and filesystem state, the MCP state is authoritative (it represents the engine's view, which includes graceful degradation to `.meta.json` internally).

## Acceptance Criteria

- AC-1: `show-status.md` uses `get_phase` MCP tool for phase detection in Sections 1, 1.5, and 2 when the MCP tool is available
- AC-2: `list-features.md` uses `get_phase` MCP tool for phase detection when the MCP tool is available
- AC-3: `finish-feature.md` Step 6a calls `complete_phase` MCP tool after updating `.meta.json`, with the `feature_type_id` in format `"feature:{id}-{slug}"`
- AC-4: When `get_phase` MCP tool is unavailable, `show-status` and `list-features` fall back to artifact-based phase detection with no user-visible difference
- AC-5: When `complete_phase` MCP tool is unavailable, `finish-feature` completes normally (`.meta.json` update succeeds), with a non-blocking warning
- AC-6: The `feature_type_id` format is `"feature:{id}-{slug}"` (e.g., `"feature:015-small-command-migration-finish"`), consistent with entity registry conventions
- AC-7: Features with `status: "planned"` bypass `get_phase` and display phase as `"planned"` directly
- AC-8: The first `get_phase` MCP failure in a multi-feature scan (show-status Section 1.5/2, list-features) causes all subsequent features in that invocation to use artifact-based fallback (fail-fast, no repeated MCP failures)

## Out of Scope

- Migrating `workflow-transitions` shared skill (`validateAndSetup`, `commitAndComplete`) — feature 016
- Migrating large commands (specify, design, create-plan, create-tasks, implement) — feature 016
- Replacing filesystem-based feature discovery with `list_features_by_status` MCP — DB completeness not guaranteed
- Entity registry status updates during finish-feature — handled separately by entity registry MCP
- Adding new tests — command files are markdown instructions, not executable code

## Technical Notes

- `get_phase` returns `FeatureWorkflowState` serialized as: `{feature_type_id, current_phase, last_completed_phase, completed_phases, mode, source, degraded}`. The `current_phase` field is the replacement for artifact-based detection. The `source` field indicates whether the state came from `"database"` or `"meta_json_fallback"`.
- `complete_phase` returns the updated `FeatureWorkflowState` after marking the phase as completed. It writes to the DB. It does NOT write to `.meta.json` — hence the dual-write pattern in FR-3.
- The `degraded` field in `get_phase` response indicates whether the engine fell back to `.meta.json` internally. This is informational and does not affect command behavior.
- MCP tool calls from commands use the standard Claude MCP tool invocation syntax. No PYTHONPATH or subprocess management is needed (unlike hook migration in feature 014).
