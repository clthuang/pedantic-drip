---
description: Show workspace dashboard with features, branches, and brainstorms
---

# /iflow:show-status Command

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `{iflow_base_branch}` — base branch for the project (default: `main`)

Display a workspace dashboard with current context, open features, and brainstorms.

## Phase Resolution Algorithm

<!-- SYNC: phase-resolution-algorithm -->

```
mcp_available = null  # tri-state: null (untested), true, false

function resolve_phase(feature_folder_name, meta_json):
    # Step 1: Skip non-active features
    if meta_json.status in ("completed", "abandoned", "planned"):
        return meta_json.status

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
- Non-active features bypass MCP entirely — their `.meta.json` status is the display value (AC-6, AC-7)
- The Step 1 filter and Step 2 MCP call use the same in-memory `.meta.json` data read at invocation start, so no race condition exists between status check and MCP call

## Section 1: Current Context

Gather via git and file inspection:

1. **Current branch**: Run `git rev-parse --abbrev-ref HEAD`
2. **Current feature**: If branch matches `feature/{id}-{slug}`, read `{iflow_artifacts_root}/features/{id}-{slug}/.meta.json` to get feature name and determine current phase using the Phase Resolution algorithm above. Show "None" if not on a feature branch.
3. **Other branches**: Run `git branch` and list all local branches except the current one. Show "None" if only one branch exists.

## Section 1.5: Project Features

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

Scan `{iflow_artifacts_root}/features/` for folders containing `.meta.json` where status is NOT `"completed"` AND `project_id` is either absent or null. This excludes project-linked features (shown in Section 1.5) and completed standalone features. If the directory does not exist, show "None".

For each open feature, show:
- **ID**: from `.meta.json`
- **Name**: the slug from `.meta.json`
- **Phase**: determined using the Phase Resolution algorithm above
- **Branch**: from `.meta.json`

If no open features exist, show "None".

## Section 3: Open Brainstorms

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

## Open Brainstorms
20260205-002937-rca-agent.prd.md (1 day ago)
20260204-secretary-agent.prd.md (2 days ago)

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

Tip: Run /iflow:create-feature or /iflow:brainstorm to start
```

## Footer Logic

- If on a feature branch with a detected phase, show: `Next: Run /iflow:{next-command} to continue` where `{next-command}` is the command for the current phase (e.g., design, create-plan, create-tasks, implement).
- If not on a feature branch, show: `Tip: Run /iflow:create-feature or /iflow:brainstorm to start`
