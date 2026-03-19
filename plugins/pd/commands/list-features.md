---
description: List all features and their branches
---

# /pd:list-features Command

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

List all features.

## Gather Features

1. **Scan {pd_artifacts_root}/features/** for feature folders. If the directory does not exist, display "No features found" and stop.
2. **Read .meta.json** from each to get branch info
3. **Determine status** from `.meta.json` for each feature. Include all statuses (active, planned, completed, abandoned).

## Phase Resolution Algorithm

<!-- SYNC: phase-resolution-algorithm — canonical copy also in show-status.md, update both identically -->

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

## For Each Feature

Determine:
- ID and name
- Current phase (using the Phase Resolution algorithm above)
- Branch name (from .meta.json, or `—` if null)
- Project (from .meta.json `project_id`, or `—` if absent/null)
- Last activity (file modification time)

## Display

```
Features:

ID   Name              Phase        Branch                          Project    Last Activity
───  ────              ─────        ──────                          ───────    ─────────────
42   user-auth         design       feature/42-user-auth            P001       2 hours ago
43   data-models       planned      —                               P001       1 day ago
41   search-feature    implement    feature/41-search-feature       —          30 min ago
40   fix-login         completed    feature/40-fix-login            —          1 day ago

Commands:
  /pd:show-status {id}  View feature details
  /pd:create-feature    Start new feature
  git checkout {branch}    Switch to feature
```

## If No Features

```
No features found.

Run /pd:create-feature "description" to start a new feature.
```
