---
name: decomposing
description: Orchestrates project decomposition -- decomposer + reviewer cycle, dependency graph, user approval, feature creation. Use when creating a project from a PRD or when the create-project command invokes decomposition.
---

# Project Decomposition

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Decomposes a project PRD into modules and features through an AI decomposer/reviewer cycle.

## Prerequisites

Expects inputs:
- `project_dir` (string): path to `{pd_artifacts_root}/projects/{id}-{slug}/`
- `prd_content` (string): full PRD markdown text
- `expected_lifetime` (string): e.g. "3-months", "6-months", "1-year", "2-years"

## Stage 1: Invoke Decomposer Agent

Dispatch decomposition via Task tool:

```
Tool: Task
subagent_type: pd:project-decomposer
model: sonnet
prompt: |
  Decompose this PRD into modules and features.

  ## PRD
  {prd_content}

  ## Constraints
  - Expected lifetime: {expected_lifetime}
  - Each feature must be a vertical slice (end-to-end value)
  - 100% coverage: every PRD requirement maps to at least one feature
  - Minimize cross-feature dependencies
  - Module boundaries should align with functional domains
  - Complexity should match expected lifetime ({shorter -> simpler})

  ## Output Format
  Return JSON:
  {
    "modules": [{"name": "...", "description": "...", "features": [{"name": "...", "description": "...", "depends_on": [], "complexity": "Low|Medium|High"}]}],
    "cross_cutting": ["..."],
    "suggested_milestones": [{"name": "...", "features": ["..."], "rationale": "..."}]
  }
```

Store the raw response as `decomposer_output`.

## Stage 2: Parse JSON Response

1. Attempt `JSON.parse(decomposer_output)`.
2. If valid JSON -> store as `decomposition` and proceed to Stage 3.
3. If invalid JSON -> retry **once**:
   - Re-invoke Stage 1 with appended message: `"\n\nYour previous response was not valid JSON. The parse error was: {error}. Return ONLY the JSON object, no prose."`
   - Parse again. If valid -> proceed to Stage 3.
4. If still invalid -> present to user:
   ```
   AskUserQuestion:
     questions: [{
       "question": "Decomposer returned invalid JSON after retry. How to proceed?",
       "header": "Parse Error",
       "options": [
         {"label": "View raw output", "description": "Display the raw decomposer response for manual inspection"},
         {"label": "Retry from scratch", "description": "Re-run decomposition with a fresh prompt"},
         {"label": "Cancel", "description": "Abort decomposition"}
       ],
       "multiSelect": false
     }]
   ```
   - "View raw output" -> display raw text, then ask user to provide corrected JSON or instructions
   - "Retry from scratch" -> go to Stage 1
   - "Cancel" -> abort, return to caller

## Stage 3: Invoke Reviewer Agent

Set `iteration = 1`. Dispatch review via Task tool:

```
Tool: Task
subagent_type: pd:project-decomposition-reviewer
model: sonnet
prompt: |
  Review this decomposition for quality.

  ## Original PRD
  {prd_content}

  ## Decomposition
  {decomposition_json}

  ## Project Context
  Expected lifetime: {expected_lifetime}

  ## Evaluation Criteria
  1. Organisational cohesion
  2. Engineering best practices (no circular deps, no god-modules)
  3. Goal alignment (serves PRD, no premature generalisation)
  4. Lifetime-scaled complexity
  5. 100% coverage

  ## Iteration
  This is iteration {iteration} of 3.

  Return JSON:
  {"approved": bool, "issues": [{"criterion": "...", "description": "...", "severity": "blocker|warning"}], "criteria_evaluated": ["..."]}
```

Parse reviewer response as JSON. If non-JSON, treat as `approved: false` with a single blocker: "Reviewer returned invalid response".

## Stage 4: Review-Fix Cycle

Max 3 iterations. After Stage 3 returns `review_result`:

1. **Determine pass/fail:**
   - **PASS:** `review_result.approved == true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** otherwise
   If PASS -> proceed to Stage 5.

2. **If `review_result.approved == false` AND `iteration < 3`:**
   - Increment `iteration`.
   - Re-invoke decomposer (Stage 1 pattern) with revision prompt:
     ```
     Tool: Task
     subagent_type: pd:project-decomposer
     model: sonnet
     prompt: |
       Revise this decomposition to address reviewer issues.

       ## PRD
       {prd_content}

       ## Previous Decomposition (to revise)
       {decomposition_json}

       ## Reviewer Issues
       {review_result.issues formatted as list}

       ## Constraints
       - Expected lifetime: {expected_lifetime}
       - Address all blocker AND warning issues
       - Preserve structure that was not flagged
       - Return the complete revised JSON (same schema)
     ```
   - Parse response (apply Stage 2 logic).
   - Store as new `decomposition`.
   - Re-invoke reviewer (Stage 3) with new decomposition and incremented iteration.

3. **If `review_result.approved == false` AND `iteration == 3`:**
   - Log remaining issues as warnings.
   - Proceed to Stage 5 with current decomposition. Note: "Decomposition approved with unresolved warnings after 3 iterations."

## Stage 5: Name-to-ID-Slug Mapping

1. Scan `{pd_artifacts_root}/features/` for all `{NNN}-*` directories. Extract numeric prefixes, find the highest `NNN`. If none exist, start at 0.
2. Flatten all features across all modules from `decomposition` into a single ordered list (preserve module order, then feature order within module).
3. Assign sequential IDs starting from `NNN + 1`.
4. Derive slug from each feature name:
   - Lowercase the name
   - Replace spaces and special characters with hyphens
   - Collapse consecutive hyphens
   - Truncate to 30 characters
   - Trim trailing hyphens
5. Build mapping table: `{ "Human Readable Name" -> "{id}-{slug}" }` for all features.
6. Remap every `depends_on` entry in `decomposition` from human-readable names to their `{id}-{slug}` equivalents using the mapping table.
7. Remap `suggested_milestones[].features` entries the same way.

Store the updated decomposition as `mapped_decomposition` and the mapping table as `name_to_id_slug`.

## Stage 6: Topological Sort and Cycle Detection

Use `tsort` for both ordering and cycle detection (tsort natively detects and reports cycles):

1. Build tsort input lines from `mapped_decomposition`:
   - For each feature with dependencies: for each dep, emit `"{dep} {feature}"` (dependency before dependent).
   - For isolated features (empty `depends_on`): emit `"{feature} {feature}"` (self-edge ensures node appears in output).
2. Pipe all lines into `tsort`:
   ```
   printf "%s\n" {all lines} | tsort 2>cycle_err
   ```
3. **If tsort succeeds** (exit 0): parse output as `execution_order` array. Set `cycle_detected = false`.
4. **If tsort fails** (exit non-zero): read stderr for cycle path. Set `cycle_detected = true`, store cycle description as `cycle_error`. Skip to Stage 7 (approval gate presents the cycle).
5. **Fallback** (if `command -v tsort` fails): Perform LLM-based topological sort with cycle check: "Order these features so each appears after all its dependencies. If a circular dependency exists, report it instead of an ordering."

## Stage 7: User Approval Gate

Initialize `refinement_count = 0`.

1. Build question text:
   - Base: `"Decomposition complete: {n} features across {m} modules. Approve?"`
   - If `cycle_detected == true`: prepend `"Warning: Circular dependency detected: {cycle_error}. Resolve by refining or cancel.\n\n"` to question text.
   - If `refinement_count >= 3`: replace question text with `"Final decision -- select one: {n} features across {m} modules."` (suppresses built-in Other option).

2. Present approval gate:
   ```
   AskUserQuestion:
     questions: [{
       "question": "{question_text}",
       "header": "Approval",
       "options": [
         {"label": "Approve", "description": "Create features and roadmap"},
         {"label": "Cancel", "description": "Save PRD without project features"}
       ],
       "multiSelect": false
     }]
   ```

3. Handle response:
   - **"Approve"** -> proceed to Stage 8.
   - **"Cancel"** -> output `"Decomposition cancelled. PRD saved at {project_dir}/prd.md."` -> STOP.
   - **"Other" (free-text)** -> capture as `refinement_feedback`. Increment `refinement_count`. If `refinement_count > 3`: ignore, re-present with Approve/Cancel only. Otherwise: re-run full decomposer+reviewer cycle (Stage 1) with previous `decomposition` + `refinement_feedback` appended to prompt, then return to Stage 7.

## Stage 8: Create Feature Directories

For each feature in `execution_order`:

1. Look up feature data from `mapped_decomposition` (name, description, module, depends_on, complexity).
2. Derive `{id}` and `{slug}` from the `{id}-{slug}` string.
3. Create directory `{pd_artifacts_root}/features/{id}-{slug}/`.
4. Call `init_feature_state` MCP tool to create the planned feature state:
   ```
   init_feature_state(
     feature_dir="{pd_artifacts_root}/features/{id}-{slug}",
     feature_id="{id}",
     slug="{slug}",
     mode="standard",
     branch="",
     status="planned"
   )
   ```
   Note: `mode` and `branch` are placeholders for planned features -- set during planned-to-active transition via `activate_feature`.

5. **Register feature entity** in the entity registry. If the MCP call fails, warn `"Entity registration failed for {id}-{slug}: {error}"` but do NOT block feature creation. Continue with the next feature.

   Build the `depends_on_features` metadata as a list of `"feature:{dep-id}-{dep-slug}"` strings from the feature's `depends_on` array.

   Call `register_entity` MCP tool:
   ```
   register_entity(
     entity_type="feature",
     entity_id="{id}-{slug}",
     name="{feature name from decomposition}",
     artifact_path="{pd_artifacts_root}/features/{id}-{slug}/",
     status="planned",
     parent_type_id="project:{project P-ID}",
     metadata='{"depends_on_features": ["feature:{dep-id}-{dep-slug}", ...]}'
   )
   ```

## Stage 9: Generate roadmap.md

Write `{project_dir}/roadmap.md` with this structure:

- H1: `Roadmap: {Project Name}`
- Comment: `<!-- Arrow: prerequisite (A before B) -->`
- H2: `Dependency Graph` -- mermaid `graph TD` block with edges:
  ```
  F{id1}[{id1}-{slug1}] --> F{id2}[{id2}-{slug2}]
  ```
- H2: `Execution Order` -- numbered list:
  ```
  1. **{id}-{slug}** -- {description} (depends on: {deps or "none"})
  ```
- H2: `Milestones` -- for each milestone, H3 `M{n}: {name}` with bullet list of `{id}-{slug}` features.
- H2: `Cross-Cutting Concerns` -- bullet list from `cross_cutting` array.

Sources:
- `execution_order` array from Stage 6 for ordering.
- `suggested_milestones` from decomposition (feature refs already remapped to ID-slugs in Stage 5).
- `cross_cutting` array directly from decomposition.
- Mermaid edges: for each feature with dependencies, emit `F{dep-id}[{dep-id}-{dep-slug}] --> F{feature-id}[{feature-id}-{feature-slug}]`.

## Stage 10: Update Project State

Call `init_project_state` MCP tool to update the project state and `.meta.json`:

1. Build `features` as a JSON array of `"{id}-{slug}"` strings in execution order.
2. Build `milestones` as a JSON array from `suggested_milestones` with feature refs as ID-slugs. Assign sequential IDs (`M1`, `M2`, ...) and set the first milestone's `status` to `"active"`, subsequent to `"planned"`:
   ```json
   [{"id": "M1", "name": "...", "status": "active", "features": ["{id}-{slug}", ...]}, {"id": "M2", "name": "...", "status": "planned", "features": [...]}]
   ```

3. Call the MCP tool:
   ```
   init_project_state(
     project_dir="{project_dir}",
     project_id="{project P-ID}",
     slug="{slug}",
     features='["{id}-{slug}", ...]',
     milestones='[{"id": "M1", ...}, ...]',
     brainstorm_source="{prd-path if applicable}"
   )
   ```

## Error Handling

| Error | Action |
|-------|--------|
| Feature directory creation fails mid-way | Keep created dirs, update project `.meta.json` with created features only |
| `roadmap.md` write fails | Warn user, continue with project `.meta.json` update |
| Project `.meta.json` update fails | Error, stop -- manual recovery needed |

## Output

After Stage 10 completes, display:

```
Project decomposition complete.
  Features: {n} created ({comma-separated list of id-slug})
  Roadmap: {project_dir}/roadmap.md
  Next: Use /show-status to see project features, or /specify --feature={first-feature} to start
```
