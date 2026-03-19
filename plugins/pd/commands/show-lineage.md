---
description: Show entity lineage — ancestry chain or descendant tree
argument-hint: [--feature=ID | --project=ID | --backlog=ID | --brainstorm=STEM] [--descendants]
---

# /pd:show-lineage Command

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Display the lineage of an entity — its ancestry chain (default) or descendant tree.

## Argument Parsing

Parse the following flags from the command arguments:

| Flag | Description |
|------|-------------|
| `--feature={id}-{slug}` or `--feature={id}` | Feature entity |
| `--project={id}` | Project entity |
| `--backlog={5-digit-id}` | Backlog entity |
| `--brainstorm={filename-stem}` | Brainstorm entity |
| `--descendants` | Show descendant tree instead of ancestry chain |

## Resolve type_id

Construct `type_id` from the provided flag using this table:

| Flag | type_id Format | Notes |
|------|---------------|-------|
| `--feature={id}-{slug}` | `feature:{id}-{slug}` | Direct: use value as-is |
| `--feature={id}` (bare 3-digit number) | Look up via `get_entity` MCP tool | If `get_entity(type_id="feature:{id}")` returns not found, glob `{pd_artifacts_root}/features/{id}-*` to find the full slug, then use `feature:{id}-{slug}` |
| `--project={id}` | `project:{id}` | Direct |
| `--backlog={5-digit-id}` | `backlog:{id}` | Direct |
| `--brainstorm={filename-stem}` | `brainstorm:{stem}` | Direct |
| (no flag, on feature branch) | `feature:{branch-suffix}` | Auto-detect from branch (see below) |

### Branch Auto-Detection

If no flag is provided:

1. Get current git branch name
2. Match against regex: `^feature/(.+)$`
3. If match: use captured group as `type_id = "feature:{captured}"`
4. If no match: **Error** — see Error Cases below

## Query Lineage

Determine direction:
- If `--descendants` flag is present: `direction = "down"`
- Otherwise: `direction = "up"` (default — show ancestry chain)

Call the `get_lineage` MCP tool:
```
get_lineage(type_id="{resolved type_id}", direction="{direction}", max_depth=10)
```

## Display Output

The `get_lineage` MCP tool returns a pre-formatted tree with Unicode box-drawing characters. Display the result directly:

**For ancestry chain (direction="up"):**
```
Lineage for feature:029-entity-lineage-tracking (ancestors):

backlog:00019 — "improve data entity lineage..." (promoted, 2026-02-27)
  └─ brainstorm:20260227-054029-entity-lineage-tracking — "Entity Lineage Tracking" (2026-02-27)
       └─ feature:029-entity-lineage-tracking — "entity-lineage-tracking" (active, 2026-02-27)
```

**For descendant tree (direction="down"):**
```
Lineage for project:P001 (descendants):

project:P001 — "Project Name" (active, 2026-03-01)
  ├─ feature:030-auth-module — "auth-module" (active, 2026-03-02)
  ├─ feature:031-api-gateway — "api-gateway" (planned, 2026-03-02)
  └─ feature:032-dashboard — "dashboard" (planned, 2026-03-02)
```

## Error Cases

### 1. Entity Not Found

If `get_lineage` returns an error indicating the entity does not exist:

```
Error: Entity "{type_id}" not found in the entity registry.

Hint: Run /pd:show-status to see known entities, or check if the entity-registry MCP server is running.
```

### 2. No Argument and No Feature Branch

If no flag is provided and the current branch does not match `^feature/(.+)$`:

```
Error: No entity specified and not on a feature branch.

Usage: /pd:show-lineage --feature=029-entity-lineage-tracking
       /pd:show-lineage --project=P001
       /pd:show-lineage --backlog=00019
       /pd:show-lineage --brainstorm=20260227-054029-entity-lineage-tracking
       /pd:show-lineage --descendants  (combine with any of the above)

Or switch to a feature branch (feature/{id}-{slug}) for auto-detection.
```

### 3. Depth Limit Reached

If the lineage result indicates traversal was truncated at >10 hops:

```
Warning: Lineage traversal reached depth limit (10 hops). Results may be incomplete.
```

Display the partial results that were returned, followed by this warning.
