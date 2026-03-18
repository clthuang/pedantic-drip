---
description: Show workspace dashboard with features, branches, and brainstorms
---

# /iflow:show-status Command

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `{iflow_base_branch}` — base branch for the project (default: `main`)

Display a workspace dashboard with current context, open features, and brainstorms.

## Data Source Detection

```
mcp_available = null  # tri-state: null (untested), true, false

# First MCP call determines data source for the entire invocation.
# Call export_entities(entity_type="feature") as the probe.
# If it succeeds → mcp_available = true, use entity registry for all sections.
# If it fails → mcp_available = false, fall through to filesystem scanning.
```

## Phase Resolution Algorithm

<!-- SYNC: phase-resolution-algorithm — canonical copy also in list-features.md, update both identically -->

```
function resolve_phase(feature_folder_name, meta_json_or_entity):
    # Step 1: Skip non-active features
    if status in ("completed", "abandoned", "planned"):
        return status

    # Step 2: Try MCP (with fail-fast)
    if mcp_available != false:
        result = call get_phase(feature_type_id="feature:{feature_folder_name}")
        if result does not contain "error": true:
            mcp_available = true
            phase = result.current_phase
            if phase is null or phase == "brainstorm":
                return "specify"
            # MCP path returns "finish" accurately; fallback cannot (shows "implement" instead)
            return phase
        else:
            mcp_available = false  # skip MCP for all remaining features

    # Step 3: Artifact-based fallback
    ARTIFACT_TO_PHASE = {
        "spec.md": "specify",
        "design.md": "design",
        "plan.md": "create-plan",
        "tasks.md": "create-tasks"
    }
    for artifact, phase in ARTIFACT_TO_PHASE.items():
        if artifact missing in feature directory:
            return phase
    return "implement"
```

**Key behaviors:**
- `mcp_available` starts as `null` (unknown), becomes `true` on first success, `false` on first failure
- Once `false`, all subsequent features in the same invocation use artifact-based fallback (AC-8, AC-9)
- Non-active features bypass MCP entirely — their status is the display value (AC-6, AC-7)

## Section 1: Current Context

Gather via git and file inspection:

1. **Current branch**: Run `git rev-parse --abbrev-ref HEAD`
2. **Current feature**: If branch matches `feature/{id}-{slug}`, read `{iflow_artifacts_root}/features/{id}-{slug}/.meta.json` to get feature name and determine current phase using the Phase Resolution algorithm above. Show "None" if not on a feature branch.
3. **Other branches**: Run `git branch` and list all local branches except the current one. Show "None" if only one branch exists.

## Section 1.5: Project Features

### MCP Path (mcp_available == true)

Use the feature entities already retrieved from `export_entities(entity_type="feature")`.

1. Filter entities where `metadata.project_id` is present and non-null
2. Group by `metadata.project_id`
3. For each project_id:
   a. Call `get_entity(type_id="project:{project_id}")` or resolve project directory via glob `{iflow_artifacts_root}/projects/{project_id}-*/` to get slug
   b. Display heading: `## Project: {project_id}-{slug}`
   c. List all features for that project as bullets — include ALL statuses (planned, active, completed, abandoned). For active features: `- {id}-{slug} ({status}, phase: {resolved_phase})` where `{resolved_phase}` comes from the Phase Resolution algorithm (call `get_phase()` per active feature). For non-active features: `- {id}-{slug} ({status})` — omit the phase annotation.

If no project-linked features, omit this section entirely.

### Filesystem Fallback (mcp_available == false)

Scan `{iflow_artifacts_root}/features/` for folders containing `.meta.json` where `project_id` is present and non-null. If the directory does not exist, skip this section entirely.

If any project-linked features found:
1. Group features by `project_id`
2. For each project_id:
   a. Resolve project directory via glob `{iflow_artifacts_root}/projects/{project_id}-*/`
   b. Read project `.meta.json` to get slug
   c. Display heading: `## Project: {project_id}-{slug}`
   d. List all features for that project as bullets — include ALL statuses (planned, active, completed, abandoned). For active features: `- {id}-{slug} ({status}, phase: {resolved_phase})` where `{resolved_phase}` comes from the Phase Resolution algorithm above. For non-active features (planned, completed, abandoned): `- {id}-{slug} ({status})` with status from `.meta.json` directly — omit the phase annotation.

If no project-linked features, omit this section entirely.

## Section 2: Open Features

### MCP Path (mcp_available == true)

Use the feature entities already retrieved from `export_entities(entity_type="feature")`.

1. Filter: exclude entities where `status == "completed"` or `status == "abandoned"` (client-side)
2. Filter: exclude entities where `metadata.project_id` is present and non-null (shown in Section 1.5)
3. For each remaining feature:
   - **ID**: from entity `entity_id`
   - **Name**: the slug portion of `entity_id`
   - **Phase**: for active features, call `get_phase(feature_type_id=entity.type_id)`. For non-active (abandoned, planned): use status directly.
   - **Branch**: from entity `metadata.branch` or construct as `feature/{entity_id}`

If no open features exist, show "None".

### Filesystem Fallback (mcp_available == false)

Scan `{iflow_artifacts_root}/features/` for folders containing `.meta.json` where status is NOT `"completed"` and NOT `"abandoned"`, AND `project_id` is either absent or null. This excludes project-linked features (shown in Section 1.5) and completed standalone features. If the directory does not exist, show "None".

For each open feature, show:
- **ID**: from `.meta.json`
- **Name**: the slug from `.meta.json`
- **Phase**: determined using the Phase Resolution algorithm above
- **Branch**: from `.meta.json`

If no open features exist, show "None".

## Section 3: Open Brainstorms

### MCP Path (mcp_available == true)

Call `export_entities(entity_type="brainstorm")` to get all brainstorm entities.

1. Filter: exclude entities where `status == "promoted"` (client-side) — AC-12
2. Filter: exclude entities where `status == "archived"` (client-side)
3. For each remaining brainstorm:
   - **Filename**: derive from `entity_id` (append `.prd.md`) or use `artifact_path` basename
   - **Age**: check `artifact_path` file modification time if file exists on disk. If file does not exist, show "(file missing)".

If no open brainstorms exist, show "None".

### Filesystem Fallback (mcp_available == false)

List files in `{iflow_artifacts_root}/brainstorms/` excluding `.gitkeep`. If the directory does not exist, show "None". For each file, show:
- Filename
- Age (e.g., "1 day ago", "3 days ago") based on file modification time

If no brainstorm files exist, show "None".

## Display Format

When on a feature branch:

```
## Current Context
Branch: feature/018-show-status-upgrade
Feature: 018-show-status-upgrade (phase: design)
Other branches: main, {iflow_base_branch}

## Project: P001-crypto-tracker
- 021-auth (active, phase: design)
- 022-data-models (planned)
- 023-dashboard (planned)

## Open Features
ID   Name                    Phase        Branch
018  show-status-upgrade     design       feature/018-show-status-upgrade
016  api-refactor            implement    feature/016-api-refactor
017  old-experiment          abandoned    feature/017-old-experiment

## Open Brainstorms
20260205-002937-rca-agent.prd.md (1 day ago)
20260204-secretary-agent.prd.md (2 days ago)

Source: entity-registry
Next: Run /iflow:design to continue
```

When not on a feature branch:

```
## Current Context
Branch: {iflow_base_branch}
Feature: None
Other branches: main

## Open Features
None

## Open Brainstorms
20260205-002937-rca-agent.prd.md (1 day ago)

Source: filesystem
Tip: Run /iflow:create-feature or /iflow:brainstorm to start
```

## Footer Logic

- Add data source line: `Source: entity-registry` when MCP path was used, `Source: filesystem` when fallback was used.
- If on a feature branch with a detected phase, show: `Next: Run /iflow:{next-command} to continue` where `{next-command}` is the command for the current phase (e.g., design, create-plan, create-tasks, implement).
- If not on a feature branch, show: `Tip: Run /iflow:create-feature or /iflow:brainstorm to start`

## Execution Summary

```
1. Section 1 (Current Context): git commands — always filesystem
2. Probe MCP: call export_entities(entity_type="feature")
   → success: mcp_available = true, cache result as feature_entities
   → failure: mcp_available = false
3. Section 1.5 (Project Features):
   → MCP: filter feature_entities by metadata.project_id
   → Fallback: scan features/ directories
4. Section 2 (Open Features):
   → MCP: filter feature_entities (exclude completed, exclude project-linked)
   → Fallback: scan features/ directories
5. Section 3 (Open Brainstorms):
   → MCP: call export_entities(entity_type="brainstorm"), filter exclude promoted/archived
   → Fallback: list brainstorms/ directory files
6. For active features in Sections 1.5 and 2: call get_phase() per feature (both paths)
7. Footer: source line + next-command/tip
```
