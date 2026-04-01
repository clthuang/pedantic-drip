---
name: workflow-state
description: Defines phase sequence and validates transitions. Use when checking phase prerequisites or managing workflow state.
---

# Workflow State Management

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Manage feature workflow state and validate phase transitions.

## Phase Sequence

The canonical workflow order:

```
brainstorm → specify → design → create-plan → implement → finish
```

### Planned→Active Transition

**YOLO Mode:** If `[YOLO_MODE]` is active, auto-select through all Planned→Active prompts:
- "Start working?" → auto "Yes"
- Mode selection → auto "Standard (Recommended)"
- Active feature conflict → auto "Continue"

When a phase command targets a feature with `status: "planned"`, handle the transition before normal validation:

1. Detect `status: "planned"` in feature `.meta.json`
2. AskUserQuestion: "Start working on {id}-{slug}? This will set it to active and create a branch."
   - Options: "Yes" / "Cancel"
   - If "Cancel": stop execution
3. AskUserQuestion: mode selection
   - Options: "Standard (Recommended)" / "Full"
4. Single-active-feature check: scan `{pd_artifacts_root}/features/` for any `.meta.json` with `status: "active"`
   - If found: AskUserQuestion "Feature {active-id}-{active-slug} is already active. Activate {id}-{slug} anyway?"
   - Options: "Continue" / "Cancel"
   - If "Cancel": stop execution
5. Call `activate_feature` MCP tool to transition the feature to active:
   ```
   activate_feature(feature_type_id="feature:{id}-{slug}")
   ```
   This sets `status` to `"active"` and projects the updated `.meta.json`.
   Note: `mode` and `branch` are set by the entity metadata. `lastCompletedPhase` is set to `"brainstorm"` (project PRD serves as brainstorm artifact, so `/specify` is a normal forward transition — no skip warning).
6. Create git branch: `git checkout -b feature/{id}-{slug}`
7. Continue with normal phase execution (proceed to workflow-transitions Step 1)

**Targeting planned features:** Users must use `--feature` argument (e.g., `/specify --feature=023-data-models`). Without `--feature`, commands scan for `status: "active"` only.

## State Schema

The `.meta.json` file in each feature folder:

```json
{
  "id": "006",
  "slug": "feature-slug",
  "mode": "standard",
  "status": "active",
  "created": "2026-01-30T00:00:00Z",
  "completed": null,
  "branch": "feature/006-feature-slug",
  "brainstorm_source": "{pd_artifacts_root}/brainstorms/20260130-143052-feature-slug.prd.md",
  "backlog_source": "00001",
  "lastCompletedPhase": "specify",
  "skippedPhases": [],
  "phases": {
    "specify": {
      "started": "2026-01-30T01:00:00Z",
      "completed": "2026-01-30T02:00:00Z",
      "iterations": 1,
      "reviewerNotes": []
    }
  }
}
```

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| id | string | Zero-padded feature number (e.g., "006") |
| slug | string | Hyphenated feature name |
| mode | string/null | One of: standard, full. Null when `status` is `planned`. |
| status | string | One of: planned, active, completed, abandoned |
| created | ISO8601 | Feature creation timestamp |
| completed | ISO8601/null | Completion timestamp (null if active or planned) |
| branch | string/null | Git branch name. Null when `status` is `planned`. |
| project_id | string/null | P-prefixed project ID (e.g., "P001") if feature belongs to a project |
| module | string/null | Module name within project |
| depends_on_features | array/null | Array of `{id}-{slug}` feature references this feature depends on |

### Source Tracking Fields

| Field | Type | Description |
|-------|------|-------------|
| brainstorm_source | string/null | Path to original PRD if promoted from brainstorm |
| backlog_source | string/null | Backlog item ID if promoted from backlog |

### Skip Tracking Fields

| Field | Type | Description |
|-------|------|-------------|
| skippedPhases | array | Record of phases skipped via soft prerequisites |

**skippedPhases Entry Structure:**
```json
{
  "phase": "design",
  "skippedAt": "2026-01-30T01:00:00Z",
  "fromPhase": "specify",
  "toPhase": "create-plan"
}
```

When user confirms skipping phases via AskUserQuestion soft prerequisite warning:
1. Build a JSON array of skipped phase entries (see structure above)
2. Pass to `transition_phase` as the `skipped_phases` parameter:
   ```
   transition_phase(
     feature_type_id="feature:{id}-{slug}",
     target_phase="{target phase}",
     yolo_active={true if YOLO_MODE else false},
     skipped_phases='[{"phase": "...", "skippedAt": "...", "fromPhase": "...", "toPhase": "..."}]'
   )
   ```
   The MCP tool stores the skipped phases and projects the updated `.meta.json`.
3. Proceed with target phase

### Phase Tracking Fields

| Field | Type | Description |
|-------|------|-------------|
| lastCompletedPhase | string/null | Last completed phase name (null until first phase completes) |
| phases | object | Phase tracking object with started/completed timestamps |

### Phase Object Structure

Each phase entry in `phases` contains:

| Field | Type | Description |
|-------|------|-------------|
| started | ISO8601 | When phase execution began |
| completed | ISO8601/null | When phase completed (null if in progress) |
| iterations | number | Number of review iterations performed |
| reviewerNotes | array | Unresolved concerns from reviewer |
| stages | object | (design phase only) Sub-stage tracking |

### Design Phase Stages Schema

See [references/design-stages-schema.md](references/design-stages-schema.md) for the full 4-stage design workflow schema, stage descriptions, field definitions, and partial recovery logic.

### Status Values

| Status | Meaning | Terminal? |
|--------|---------|-----------|
| planned | Created by decomposition, not yet started | No |
| active | Work in progress | No |
| completed | Merged/finished successfully | Yes |
| abandoned | Discarded intentionally | Yes |

When `status` is `planned`, `mode` and `branch` are `null`. These fields are set when the feature transitions to `active`.

Terminal statuses cannot be changed. New work requires a new feature.

### Status Updates

The `/pd:finish-feature` command updates status to terminal values:

```json
// For completed features
{ "status": "completed", "completed": "{ISO timestamp}" }

// For abandoned features
{ "status": "abandoned", "completed": "{ISO timestamp}" }
```

## Review History

During development, `.review-history.md` tracks iteration feedback.
On `/pd:finish-feature`, this file is deleted (git has the permanent record).
