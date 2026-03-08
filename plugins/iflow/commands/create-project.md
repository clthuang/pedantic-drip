---
description: Create a project and invoke decomposition
argument-hint: --prd=<path>
---

# /iflow:create-project Command

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Create a project from a PRD and invoke AI-driven decomposition into features.

## Step 1: Accept PRD

Receive `--prd={path}` argument (from brainstorming (PRD-ready) or standalone invocation).

If no `--prd` argument: ask user for PRD path via AskUserQuestion.

## Step 2: Validate PRD

1. Check PRD file exists at path
2. Check file is non-empty (> 100 bytes)
3. If validation fails: show error, stop

## Step 3: Derive Project ID

1. Scan `{iflow_artifacts_root}/projects/` for existing `P{NNN}-*` directories
2. Extract highest NNN, increment by 1
3. If no projects exist, start at P001
4. Zero-pad to 3 digits

## Step 4: Derive Slug

1. Extract title from PRD first heading (e.g., `# PRD: Feature Name` → `feature-name`)
2. Lowercase, replace spaces/special chars with hyphens, max 30 chars, trim trailing hyphens

## Step 5: Prompt Expected Lifetime

```
AskUserQuestion:
  questions: [{
    "question": "What is the expected project lifetime?",
    "header": "Lifetime",
    "options": [
      {"label": "3-months", "description": "Short-lived project"},
      {"label": "6-months", "description": "Medium-term project"},
      {"label": "1-year (Recommended)", "description": "Standard project lifetime"},
      {"label": "2-years", "description": "Long-lived project"}
    ],
    "multiSelect": false
  }]
```

## Step 6: Create Project Directory

1. Create `{iflow_artifacts_root}/projects/` if it doesn't exist
2. Create `{iflow_artifacts_root}/projects/P{NNN}-{slug}/`

## Step 7: Create Project State

Call `init_project_state` MCP tool to create the project state and `.meta.json`:

```
init_project_state(
  project_dir="{iflow_artifacts_root}/projects/P{NNN}-{slug}",
  project_id="P{NNN}",
  slug="{slug}",
  features='[]',
  milestones='[]',
  brainstorm_source="{prd-path}"
)
```

The MCP tool creates the `.meta.json` with proper structure including `id`, `slug`, `status`, `created` timestamp, `features`, `milestones`, and `brainstorm_source`.

## Step 8: Copy PRD

1. Copy PRD content to `{iflow_artifacts_root}/projects/P{NNN}-{slug}/prd.md`
2. Verify copy: confirm destination file exists and is non-empty
3. If verification fails: show error, stop

## Step 8b: Register Entities

After the PRD is copied, register entities in the entity registry. All MCP calls are wrapped in failure handling: if any MCP call fails, warn `"Entity registration failed: {error}"` but do NOT block project creation. Continue with Step 9.

### 1. Parse Brainstorm for Backlog Source

Read the copied PRD content from `{iflow_artifacts_root}/projects/P{NNN}-{slug}/prd.md`.

Parse for backlog source marker using pattern `\*Source: Backlog #(\d{5})\*`.

Extract the brainstorm filename stem from the `--prd` path (e.g., `20260227-054029-entity-lineage-tracking` from `{iflow_artifacts_root}/brainstorms/20260227-054029-entity-lineage-tracking.prd.md`).

### 2. Register Backlog Entity (if backlog marker found)

If the backlog source pattern matched:

```
register_entity(
  entity_type="backlog",
  entity_id="{5-digit backlog id}",
  name="Backlog #{id}",
  status="promoted"
)
```

Set the brainstorm-to-backlog parent relationship:
```
set_parent(
  type_id="brainstorm:{filename-stem}",
  parent_type_id="backlog:{5-digit backlog id}"
)
```

### 3. Register Brainstorm Entity

Extract the title from the PRD first heading (e.g., `# PRD: Feature Name` -> `Feature Name`).

```
register_entity(
  entity_type="brainstorm",
  entity_id="{filename-stem}",
  name="{title}",
  artifact_path="{prd-path}"
)
```

### 4. Register Project Entity

```
register_entity(
  entity_type="project",
  entity_id="P{NNN}",
  name="{slug}",
  artifact_path="{iflow_artifacts_root}/projects/P{NNN}-{slug}/",
  status="active",
  parent_type_id="brainstorm:{filename-stem}"
)
```

## Step 9: Output

```
Project P{NNN}-{slug} created
  Lifetime: {expected_lifetime}
  Directory: {iflow_artifacts_root}/projects/P{NNN}-{slug}/
  PRD: Copied

Invoking decomposition...
```

## Step 10: Invoke Decomposition

Invoke the decomposing skill as inline continuation (not subprocess). Pass context:
- `project_dir`: `{iflow_artifacts_root}/projects/P{NNN}-{slug}/`
- `prd_content`: full PRD markdown text
- `expected_lifetime`: selected lifetime value

Follow the decomposing skill steps from this point forward.

## Error Handling

| Error | Action |
|-------|--------|
| PRD file not found | Show error with path, stop |
| PRD file empty | Show error, stop |
| PRD copy verification fails | Show error, stop |
| `{iflow_artifacts_root}/projects/` doesn't exist | Create it (Step 6) |
