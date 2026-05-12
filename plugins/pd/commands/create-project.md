---
description: Create a project and invoke decomposition
argument-hint: --prd=<path>
---

# /pd:create-project Command

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Create a project from a PRD and invoke AI-driven decomposition into features.

## Step 1: Accept PRD

Receive `--prd={path}` argument (from brainstorming (PRD-ready) or standalone invocation).

If no `--prd` argument: ask user for PRD path via AskUserQuestion.

## Step 2: Validate PRD

1. Check PRD file exists at path
2. Check file is non-empty (> 100 bytes)
3. If validation fails: show error, stop

## Step 3: Derive Project ID

1. Scan `{pd_artifacts_root}/projects/` for existing `P{NNN}-*` directories
2. Extract highest NNN, increment by 1
3. If no projects exist, start at P001
4. Zero-pad to 3 digits

## Step 4: Derive Slug

1. Extract title from PRD first heading (e.g., `# PRD: Feature Name` → `feature-name`)
2. Lowercase, replace spaces/special chars with hyphens, max 30 chars, trim trailing hyphens

## Step 5: Create Project Directory

1. Create `{pd_artifacts_root}/projects/` if it doesn't exist
2. Create `{pd_artifacts_root}/projects/P{NNN}-{slug}/`

## Step 7: Create Project State

Call `init_project_state` MCP tool to create the project state and `.meta.json`:

```
init_project_state(
  project_dir="{pd_artifacts_root}/projects/P{NNN}-{slug}",
  project_id="P{NNN}",
  slug="{slug}",
  features='[]',
  milestones='[]',
  brainstorm_source="{prd-path}"
)
```

The MCP tool creates the `.meta.json` with required fields: `id`, `slug`, `status`, `created` timestamp, `features`, `milestones`, and `brainstorm_source`.

## Step 8: Copy PRD

1. Copy PRD content to `{pd_artifacts_root}/projects/P{NNN}-{slug}/prd.md`
2. Verify copy: confirm destination file exists and is non-empty
3. If verification fails: show error, stop

## Step 8b: Register Entities

After the PRD is copied, register entities in the entity registry. All MCP calls are wrapped in failure handling: if any MCP call fails, warn `"Entity registration failed: {error}"` but do NOT block project creation. Continue with Step 9.

### 1. Parse Brainstorm for Backlog Source

Read the copied PRD content from `{pd_artifacts_root}/projects/P{NNN}-{slug}/prd.md`.

Parse for backlog source marker using pattern `\*Source: Backlog #(\d{5})\*`.

Extract the brainstorm filename stem from the `--prd` path (e.g., `20260227-054029-entity-lineage-tracking` from `{pd_artifacts_root}/brainstorms/20260227-054029-entity-lineage-tracking.prd.md`).

### 2. Register Backlog Entity (if backlog marker found)

If the backlog source pattern matched. The MCP entity_server translates
`EntityExistsError` to a structured JSON error (`error_type=entity_exists`,
with `recovery_hint`) per feature 109 design §3.5; if the backlog id is
already registered, surface the error or fall back to `upsert_entity`:

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
  parent_ref="backlog:{5-digit backlog id}"
)
```

### 3. Register Brainstorm Entity

Extract the title from the PRD first heading (e.g., `# PRD: Feature Name` -> `Feature Name`).
The MCP entity_server translates `EntityExistsError` to structured JSON
(`error_type=entity_exists`) per feature 109 design §3.5; on conflict,
surface the error or fall back to `upsert_entity`:

```
register_entity(
  entity_type="brainstorm",
  entity_id="{filename-stem}",
  name="{title}",
  artifact_path="{prd-path}"
)
```

### 4. Register Project Entity

First resolve the brainstorm parent: `get_entity(ref="brainstorm:{filename-stem}")` → capture `uuid` as `brainstorm_uuid`.
Same MCP routing: `EntityExistsError` returns structured JSON per
feature 109 design §3.5:

```
register_entity(
  entity_type="project",
  entity_id="P{NNN}",
  name="{slug}",
  artifact_path="{pd_artifacts_root}/projects/P{NNN}-{slug}/",
  status="active",
  parent_uuid="{brainstorm_uuid}"
)
```

## Step 9: Output

```
Project P{NNN}-{slug} created
  Directory: {pd_artifacts_root}/projects/P{NNN}-{slug}/
  PRD: Copied

Invoking decomposition...
```

## Step 10: Invoke Decomposition

Invoke the decomposing skill as inline continuation (not subprocess). Pass context:
- `project_dir`: `{pd_artifacts_root}/projects/P{NNN}-{slug}/`
- `prd_content`: full PRD markdown text

Follow the decomposing skill steps from this point forward.

## Error Handling

| Error | Action |
|-------|--------|
| PRD file not found | Show error with path, stop |
| PRD file empty | Show error, stop |
| PRD copy verification fails | Show error, stop |
| `{pd_artifacts_root}/projects/` doesn't exist | Create it (Step 6) |
