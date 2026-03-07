---
name: workflow-transitions
description: Shared workflow boilerplate for phase commands. Use when a command needs to validate transitions, check branches, handle partial phases, mark started, auto-commit, and update state.
---

# Workflow Transitions

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Shared procedures used by all phase commands (specify, design, create-plan, create-tasks, implement, finish). Commands reference these procedures instead of inlining identical boilerplate.

## YOLO Mode Overrides

If the current execution context contains `[YOLO_MODE]`:

**All AskUserQuestion calls in validateAndSetup auto-select:**
- Backward warning → auto "Continue"
- Skip warning → auto "Continue" (record skips in .meta.json)
- Branch mismatch → auto "Switch"
- Partial phase recovery → auto "Continue" (resume)

**Context propagation rule:**
When invoking any subsequent command or skill, always include `[YOLO_MODE]` in the args.
This ensures autonomous mode propagates through the entire command chain.

## validateAndSetup(phaseName)

Execute steps 1-3 in order. Stop on any blocking result.

### Step 1: Validate Transition

Check transition validity:
- Read current `.meta.json` state (get `lastCompletedPhase`)
- Hard prerequisites are validated by the calling command before Step 1
- Determine transition type: normal forward, backward, or skip
- If blocked by command prerequisite: command already stopped before reaching Step 1

**If backward** (re-running completed phase):
```
AskUserQuestion:
  questions: [{
    "question": "Phase '{phaseName}' was already completed. Re-running will update timestamps but not undo previous work. Continue?",
    "header": "Backward",
    "options": [
      {"label": "Continue", "description": "Re-run the phase"},
      {"label": "Cancel", "description": "Stay at current phase"}
    ],
    "multiSelect": false
  }]
```
If "Cancel": Stop execution.

**If warning** (skipping phases):
```
AskUserQuestion:
  questions: [{
    "question": "Skipping {skipped phases}. This may reduce artifact quality. Continue anyway?",
    "header": "Skip",
    "options": [
      {"label": "Continue", "description": "Proceed despite skipping phases"},
      {"label": "Stop", "description": "Return to complete skipped phases"}
    ],
    "multiSelect": false
  }]
```
If "Continue": Record skipped phases in `.meta.json` skippedPhases array, then proceed.
If "Stop": Stop execution.

### Step 2: Check Branch

If feature has a branch defined in `.meta.json`:
- Get current branch: `git branch --show-current`
- If current branch != expected branch, use AskUserQuestion:
  ```
  AskUserQuestion:
    questions: [{
      "question": "You're on '{current}', but feature uses '{expected}'. Switch branches?",
      "header": "Branch",
      "options": [
        {"label": "Switch", "description": "Run: git checkout {expected}"},
        {"label": "Continue", "description": "Stay on {current}"}
      ],
      "multiSelect": false
    }]
  ```
- Skip this check if branch is null (legacy feature)

### Step 3: Check for Partial Phase

If `phases.{phaseName}.started` exists but `phases.{phaseName}.completed` is null:
```
AskUserQuestion:
  questions: [{
    "question": "Detected partial {phaseName} work. How to proceed?",
    "header": "Recovery",
    "options": [
      {"label": "Continue", "description": "Resume from where you left off"},
      {"label": "Start Fresh", "description": "Discard and begin new"},
      {"label": "Review First", "description": "View progress before deciding"}
    ],
    "multiSelect": false
  }]
```

### Step 4: Mark Phase Started

Update `.meta.json`:
```json
{
  "phases": {
    "{phaseName}": {
      "started": "{ISO timestamp}"
    }
  }
}
```

**Sync to workflow DB (best-effort):**

After the `.meta.json` update above, sync the phase transition to the workflow database:

1. Construct `feature_type_id` as `"feature:{id}-{slug}"` from the `.meta.json` `id` and `slug` fields (available from the `.meta.json` read in Step 1). This is the same value as `entity_type_id` used elsewhere in this skill.
2. Call `transition_phase(feature_type_id, "{phaseName}")`.
   - If `[YOLO_MODE]` is active in the current context: include `yolo_active=true`.
   - If `[YOLO_MODE]` is NOT active: omit `yolo_active` (defaults to `false`).
3. If the call succeeds (response contains `transitioned: true` and `degraded: false`): no output, proceed to Step 5.
4. If the call fails for any reason (MCP tool unavailable, response contains `error: true`, `transitioned: false`, `degraded: true`, or response is not valid JSON):
   output `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`
   where `{reason}` is a brief description (e.g., "MCP tool unavailable", "transition rejected", "feature not found").
   Do NOT block — the `.meta.json` update already succeeded.

Note: On partial-phase resume (Step 3 → "Continue"), this call may target a phase already active in the DB. The engine handles re-entry gracefully; any rejection is covered by step 4's warn-and-continue.

### Step 5: Inject Project Context (conditional)

If feature `.meta.json` has no `project_id` (null or absent): skip Step 5 entirely.

If `project_id` is present:

1. Resolve project directory: glob `{iflow_artifacts_root}/projects/{project_id}-*/`
2. If directory not found: warn "Project artifacts missing for {project_id}, proceeding without project context" → skip remaining sub-steps
3. Read `{project_dir}/prd.md` → store as `project_prd`
4. Read `{project_dir}/roadmap.md` → store as `project_roadmap` (if not found: warn, set empty)
5. For each `feature_ref` in `depends_on_features`:
   a. Resolve feature directory: glob `{iflow_artifacts_root}/features/{feature_ref}/`
   b. Read feature `.meta.json`, check `status == "completed"`
   c. If completed: read `spec.md` and `design.md`
   d. Store as `dependency_context[]`
6. Format as markdown:
   ```
   ## Project Context
   ### Project PRD
   {project_prd}
   ### Roadmap
   {project_roadmap}
   ### Completed Dependency: {feature_ref}
   #### Spec
   {spec content}
   #### Design
   {design content}
   ```
7. Prepend to phase input context
8. Each read can fail independently — missing project dir skips all, missing roadmap warns, missing dependency artifacts skip that dependency

#### Reviewer Prompt Instruction

When constructing reviewer prompts and the feature has no local `prd.md`, use the project PRD from the `## Project Context` section above. If neither local `prd.md` nor project context exists, use `"None — feature created without brainstorm"` as the PRD slot value.

## commitAndComplete(phaseName, artifacts[])

Execute after phase work and reviews are done.

### Step 1: Auto-Commit

**Frontmatter injection (before git add):**

For each artifact file being committed, invoke the frontmatter injection CLI
to embed entity identity headers. Resolve the plugin root using the
two-location pattern. Construct `entity_type_id` as `"feature:{id}-{slug}"`
from `.meta.json`. Suppress stderr and ignore non-zero exit (fail-open).

```
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/iflow*/*/hooks 2>/dev/null | head -1 | xargs dirname)
if [ -z "$PLUGIN_ROOT" ]; then PLUGIN_ROOT="plugins/iflow"; fi  # Fallback (dev workspace)
for artifact in {artifacts}; do
  "$PLUGIN_ROOT/.venv/bin/python" \
    "$PLUGIN_ROOT/hooks/lib/entity_registry/frontmatter_inject.py" \
    "$artifact" "feature:{id}-{slug}" 2>/dev/null || true
done
```

```bash
git add {artifacts joined by space} {iflow_artifacts_root}/features/{id}-{slug}/.meta.json {iflow_artifacts_root}/features/{id}-{slug}/.review-history.md
git commit -m "phase({phaseName}): {slug} - approved"
git push
```

**Error handling:**
- On commit failure: Display error, do NOT mark phase completed, allow retry
- On push failure: Commit succeeds locally, warn user with "Run: git push" instruction, mark phase completed

### Step 2: Update State

Update `.meta.json`:
```json
{
  "phases": {
    "{phaseName}": {
      "completed": "{ISO timestamp}",
      "iterations": {count},
      "reviewerNotes": ["any unresolved concerns"]
    }
  },
  "lastCompletedPhase": "{phaseName}"
}
```

**Sync to workflow DB (best-effort):**

After the `.meta.json` update above, sync the phase completion to the workflow database:

1. Construct `feature_type_id` as `"feature:{id}-{slug}"` from `.meta.json` `id` and `slug` fields (same value used in `validateAndSetup` Step 4, and as `entity_type_id` in Step 1 frontmatter injection).
2. Call `complete_phase(feature_type_id, "{phaseName}")`.
3. If the call succeeds: no output, proceed.
4. If the call fails for any reason (MCP tool unavailable, response contains `error: true`, or response is not valid JSON):
   output `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`
   where `{reason}` is a brief description (e.g., "MCP tool unavailable", "phase mismatch", "feature not found").
   Do NOT block — the `.meta.json` update already succeeded.
