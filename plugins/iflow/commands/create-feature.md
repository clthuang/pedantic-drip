---
description: Alternative entry point - skip brainstorming and create feature directly
argument-hint: <feature-description> [--prd=<path>]
---

# /iflow:create-feature Command

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

**Alternative entry point** for feature development. Use when you want to skip brainstorming.

Recommended flow: `/iflow:brainstorm` → (promotion) → `/iflow:specify` → ...
This command: `/iflow:create-feature` → `/iflow:specify` → ... (skips exploration)

## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- Active feature conflict → auto "Create new anyway"
- Mode selection → auto "Standard (Recommended)"
- Context propagation: when auto-invoking specify, include `[YOLO_MODE]` in args

## Check for Active Feature

Before creating, check if a feature is already active:

1. Look in `{iflow_artifacts_root}/features/` for folders with `.meta.json` where `status: "active"`
2. If found:
   ```
   AskUserQuestion:
     questions: [{
       "question": "Feature {id}-{slug} is already active. What would you like to do?",
       "header": "Active Feature",
       "options": [
         {"label": "Continue with existing", "description": "Show status and stop"},
         {"label": "Create new anyway", "description": "Proceed with new feature creation"}
       ],
       "multiSelect": false
     }]
   ```
3. If "Continue with existing": Invoke `/iflow:show-status` → STOP
4. If "Create new anyway": Proceed with creation below

## Gather Information

1. **Get feature description** from argument or ask user
2. **Determine feature ID**: Find highest number in `{iflow_artifacts_root}/features/` and add 1
3. **Create slug** from description (lowercase, hyphens, max 30 chars)

## Suggest Workflow Mode

Based on described scope, suggest a mode:

| Scope | Suggested Mode |
|-------|----------------|
| Most features, clear scope | Standard |
| "rewrite", "refactor system", "breaking change" | Full |

Present mode selection via AskUserQuestion:
```
AskUserQuestion:
  questions: [{
    "question": "Feature: {id}-{slug}. Select workflow mode:",
    "header": "Mode",
    "options": [
      {"label": "Standard (Recommended)", "description": "All phases with optional verification"},
      {"label": "Full", "description": "All phases with required verification"}
    ],
    "multiSelect": false
  }]
```

Note: If "Full" indicators are detected in the description, swap the recommended label to Full.

## Create Feature

### For All Modes

0. Ensure parent exists: `mkdir -p {iflow_artifacts_root}/features/`
1. Create folder: `{iflow_artifacts_root}/features/{id}-{slug}/`
2. Create feature branch:
   ```bash
   git checkout -b feature/{id}-{slug}
   ```
3. Create `.meta.json` (see below)

### Mode-Specific Behavior

**Standard/Full:**
- Inform: "Created branch feature/{id}-{slug}."
- Inform: "Continuing to /iflow:specify..."
- Auto-invoke `/iflow:specify`

## Create Metadata File

Call `init_feature_state` MCP tool to create the feature state and `.meta.json`:

```
init_feature_state(
  feature_dir="{iflow_artifacts_root}/features/{id}-{slug}",
  feature_id="{id}",
  slug="{slug}",
  mode="{selected-mode}",
  branch="feature/{id}-{slug}",
  brainstorm_source="{path-to-brainstorm-if-promoted}",
  status="active"
)
```

Notes:
- `brainstorm_source` is only included when feature is promoted from a brainstorm — omit the parameter if not applicable
- The MCP tool creates the `.meta.json` with proper structure (phases, lastCompletedPhase, timestamps)
- The tool returns `feature_type_id` and `meta_json_path` in its response

## Handle PRD Source

If `--prd` argument provided (promotion from brainstorm):

1. Copy the PRD file: `{prd-path}` → `{iflow_artifacts_root}/features/{id}-{slug}/prd.md`
2. **Verify copy succeeded:** Confirm destination file exists and is non-empty
3. If verification fails: Output error and STOP
4. The `brainstorm_source` is already passed to `init_feature_state` above

If `--prd` NOT provided (direct creation):
- No PRD file is created
- `brainstorm_source` is not set in `.meta.json`

## Handle Backlog Source

If feature was promoted from a brainstorm that originated from a backlog item:

1. **Read brainstorm content** from `brainstorm_source` path in context
2. **Parse for backlog source** using pattern `\*Source: Backlog #(\d{5})\*`
3. **If found:**
   - Include `backlog_source="{id}"` in the `init_feature_state` call above
   - Read `{iflow_artifacts_root}/backlog.md`
   - Find row matching `| {id} |`
   - **Annotate the row** (do NOT remove it):
     - If the Description column does NOT contain `(promoted →`: append ` (promoted → feature:{id}-{slug})` to the Description column
     - If the Description column already contains `(promoted → ...)`: replace the closing `)` with `, feature:{id}-{slug})` (supports multiple promotions)
   - Write updated backlog
   - Display: `Linked from backlog item #{id} (promoted)`
4. **If pattern not found:** No action, continue normally
5. **If ID found but row missing:** Display warning `⚠️ Backlog item #{id} not found in {iflow_artifacts_root}/backlog.md`, continue with feature creation

## Register Entities

After Handle PRD Source and Handle Backlog Source sections complete, register entities in the entity registry. All MCP calls are wrapped in failure handling: if any MCP call fails, warn `"Entity registration failed: {error}"` but do NOT block feature creation. Continue with the rest of the command.

### 1. Register Backlog Entity (if backlog_source found)

If `backlog_source` was found in the Handle Backlog Source step:

Call `register_entity` MCP tool (idempotent — safe if entity already exists):
```
register_entity(
  entity_type="backlog",
  entity_id="{backlog_source id}",
  name="{description text from the backlog.md row}",
  status="promoted"
)
```

### 2. Register Brainstorm Entity (if brainstorm_source found)

If `brainstorm_source` was set (i.e., `--prd` was provided):

Extract the filename stem from the brainstorm_source path (e.g., `20260227-054029-entity-lineage-tracking` from `{iflow_artifacts_root}/brainstorms/20260227-054029-entity-lineage-tracking.prd.md`).

Call `register_entity` MCP tool (idempotent):
```
register_entity(
  entity_type="brainstorm",
  entity_id="{filename-stem}",
  name="{slug}",
  artifact_path="{brainstorm_source path}"
)
```

If brainstorm has a backlog parent (backlog_source was found), set the parent relationship:
```
set_parent(
  type_id="brainstorm:{filename-stem}",
  parent_type_id="backlog:{backlog_source id}"
)
```

### 3. Register Feature Entity

Derive the parent_type_id:
- If `brainstorm_source` exists: `parent_type_id = "brainstorm:{filename-stem}"`
- Else if `backlog_source` exists (no brainstorm): `parent_type_id = "backlog:{backlog_source id}"`
- Else: `parent_type_id = null` (no parent)

Call `register_entity` MCP tool:
```
register_entity(
  entity_type="feature",
  entity_id="{id}-{slug}",
  name="{slug}",
  artifact_path="{iflow_artifacts_root}/features/{id}-{slug}/",
  status="active",
  parent_type_id="{derived parent_type_id}"
)
```

## State Tracking

Apply the detecting-kanban skill:
1. If Vibe-Kanban available:
   - Create card with feature name
   - Set status to "New"
2. Otherwise:
   - Use TodoWrite to track feature

## Output

**If `--prd` provided (promotion from brainstorm):**
```
✓ Feature {id}-{slug} created
  Mode: {mode}
  Folder: {iflow_artifacts_root}/features/{id}-{slug}/
  Branch: feature/{id}-{slug}
  PRD: Copied from brainstorm
  Linked from: Backlog #{backlog_id} (promoted)  ← only if backlog source found
```

**If `--prd` NOT provided (direct creation):**
```
✓ Feature {id}-{slug} created
  Mode: {mode}
  Folder: {iflow_artifacts_root}/features/{id}-{slug}/
  Branch: feature/{id}-{slug}
  Linked from: Backlog #{backlog_id} (promoted)  ← only if backlog source found

  Note: No PRD. /specify will gather requirements.
```

## Auto-Continue

After creation, automatically invoke `/iflow:specify --feature={id}-{slug}`.
