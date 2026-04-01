---
name: workflow-transitions
description: Shared workflow boilerplate for phase commands. Use when a command needs to validate transitions, check branches, handle partial phases, mark started, auto-commit, and update state.
---

# Workflow Transitions

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Shared procedures used by all phase commands (specify, design, create-plan, implement, finish). Commands reference these procedures instead of inlining identical boilerplate.

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
If "Continue": Pass skipped phases to `transition_phase` via `skipped_phases` parameter (see workflow-state skill), then proceed.
If "Stop": Stop execution.

### Step 1b: Backward Context Injection

After Step 1 completes, check for backward travel context:

1. Read .meta.json (already read in Step 1)
2. If `backward_context` field exists in .meta.json:
   a. Format as markdown block:
      ```
      ## Backward Travel Context
      This phase is being re-run because a downstream reviewer identified
      issues rooted here.

      **Source:** {backward_context.source_phase} reviewer
      **Findings:**
      {for each finding in backward_context.findings:
        - [{finding.artifact}] {finding.section}: {finding.issue}
          Suggestion: {finding.suggestion}}
      **Downstream Impact:** {backward_context.downstream_impact}

      Address these findings in this phase's artifact revision.
      ```
   b. Prepend this block to the phase's prompt context (before any skill invocation)
   c. If backward_to targets "brainstorm": add "Run in clarification mode — research stages already completed. Focus on refining the identified issue."
3. If `backward_context` does NOT exist: normal flow (no injection)
4. After the phase completes successfully: clear `backward_context` from entity metadata via `update_entity(type_id, metadata={"backward_context": null})`

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

Call `transition_phase` MCP tool to record the phase start and update `.meta.json`:

1. Construct `feature_type_id` as `"feature:{id}-{slug}"` from the `.meta.json` `id` and `slug` fields (available from the `.meta.json` read in Step 1). This is the same value as `entity_type_id` used elsewhere in this skill.
2. Call `transition_phase(feature_type_id, "{phaseName}")`.
   - If `[YOLO_MODE]` is active in the current context: include `yolo_active=true`.
   - If `[YOLO_MODE]` is NOT active: omit `yolo_active` (defaults to `false`).
3. If the call succeeds (response contains `transitioned: true`): the `started_at` field in the response contains the phase start timestamp. The tool automatically updates the DB and projects `.meta.json`. Proceed to Step 5.
4. If the call fails for any reason (MCP tool unavailable, response contains `error: true`, `transitioned: false`, `degraded: true`, or response is not valid JSON):
   output `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`
   where `{reason}` is a brief description (e.g., "MCP tool unavailable", "transition rejected", "feature not found").
   Do NOT block — proceed to Step 5 regardless.

Note: On partial-phase resume (Step 3 -> "Continue"), this call may target a phase already active in the DB. The engine handles re-entry gracefully; any rejection is covered by step 4's warn-and-continue.

### Step 5: Inject Project Context (conditional)

If feature `.meta.json` has no `project_id` (null or absent): skip Step 5 entirely.

If `project_id` is present:

1. Resolve project directory: glob `{pd_artifacts_root}/projects/{project_id}-*/`
2. If directory not found: warn "Project artifacts missing for {project_id}, proceeding without project context" → skip remaining sub-steps
3. Read `{project_dir}/prd.md` → store as `project_prd`
4. Read `{project_dir}/roadmap.md` → store as `project_roadmap` (if not found: warn, set empty)
5. For each `feature_ref` in `depends_on_features`:
   a. Resolve feature directory: glob `{pd_artifacts_root}/features/{feature_ref}/`
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

## commitAndComplete(phaseName, artifacts[], iterations, capReached, reviewerNotes[])

Execute after phase work and reviews are done.

**Parameters:**
- `phaseName` (string): Phase name for commit message and summary header.
- `artifacts[]` (string[]): File paths for git staging. When empty, Step 1 commits only .meta.json and .review-history.md.
- `iterations` (integer): Combined review loop counter at exit. For single-stage phases: the loop counter. For dual-stage phases (specify, design, create-plan): `step1_iterations + phase_iterations`. For reset cases ("Fix and rerun"): counter from the final run only.
- `capReached` (boolean): Whether any reviewer stage hit its max iteration limit without approval.
- `reviewerNotes[]` (object[]): Unresolved reviewer issues. Each object: `{"severity": "blocker"|"warning"|"suggestion", "description": "..."}`.

### Step 1: Auto-Commit

**Frontmatter injection (before git add):**

For each artifact file being committed, invoke the frontmatter injection CLI
to embed entity identity headers. Resolve the plugin root using the
two-location pattern. Construct `entity_type_id` as `"feature:{id}-{slug}"`
from `.meta.json`. Suppress stderr and ignore non-zero exit (fail-open).

```
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
if [ -z "$PLUGIN_ROOT" ]; then PLUGIN_ROOT="plugins/pd"; fi  # Fallback (dev workspace)
for artifact in {artifacts}; do
  "$PLUGIN_ROOT/.venv/bin/python" \
    "$PLUGIN_ROOT/hooks/lib/entity_registry/frontmatter_inject.py" \
    "$artifact" "feature:{id}-{slug}" 2>/dev/null || true
done
```

```bash
git add {artifacts joined by space} {pd_artifacts_root}/features/{id}-{slug}/.meta.json {pd_artifacts_root}/features/{id}-{slug}/.review-history.md
git commit -m "phase({phaseName}): {slug} - approved"
git push
```

**Error handling:**
- On nothing to commit (git commit output contains "nothing to commit"): Treat as success — skip to Step 2. This handles the implement phase where review-loop commits may have already staged .meta.json/.review-history.md.
- On commit failure: Display error, do NOT mark phase completed, allow retry
- On push failure: Commit succeeds locally, warn user with "Run: git push" instruction, mark phase completed

### Step 2: Update State

Call `complete_phase` MCP tool to record the phase completion, timing data, and update `.meta.json`:

1. Construct `feature_type_id` as `"feature:{id}-{slug}"` from `.meta.json` `id` and `slug` fields (same value used in `validateAndSetup` Step 4, and as `entity_type_id` in Step 1 frontmatter injection).
2. Call the MCP tool:
   ```
   complete_phase(
     feature_type_id="feature:{id}-{slug}",
     phase="{phaseName}",
     iterations={iterations},
     reviewer_notes='{JSON array of reviewerNotes[].map(n => n.description)}'
   )
   ```
   The tool stores `completed` timestamp, `iterations`, `reviewerNotes`, and `lastCompletedPhase` in the DB and projects the updated `.meta.json`. The `completed_at` field in the response contains the completion timestamp.
3. If the call succeeds: no output, proceed.
4. If the call fails for any reason (MCP tool unavailable, response contains `error: true`, or response is not valid JSON):
   output `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.`
   where `{reason}` is a brief description (e.g., "MCP tool unavailable", "phase mismatch", "feature not found").
   Do NOT block — proceed regardless.

### Step 3: Phase Summary

> **Note:** Before generating the Phase Summary, run handleReviewerResponse (see below) to determine if the reviewer recommended backward travel. If handleReviewerResponse returns "backward", skip commitAndComplete entirely and transition to the backward target phase instead.

Output a plain-text summary block (max 12 lines) before returning control to the calling command's AskUserQuestion prompt.

**Outcome decision table** (evaluate top to bottom, first match wins):
1. `capReached == true` → outcome = "Review cap reached."
2. `iterations == 1` AND `reviewerNotes` is empty → outcome = "Approved on first pass."
3. `iterations > 1` AND `reviewerNotes` is empty → outcome = "Approved after {iterations} iterations."
4. `reviewerNotes` is non-empty → outcome = "Approved with notes."

**Output format:**

```
{PhaseName} complete ({iterations} iteration(s)). {outcome}
Artifacts: {comma-separated artifact filenames}
{feedback_section}
```

- **Artifacts line:** Derived from `artifacts[]` parameter. Omit this line entirely when `artifacts[]` is empty.
- **Feedback section (when `reviewerNotes[]` is non-empty):**
  - Normal header: `"Remaining feedback ({W} warnings, {S} suggestions):"`
  - Cap-reached header: `"Unresolved issues carried forward:"`
  - List items sorted by severity (warnings first, then suggestions). Blocker-severity items (present only when capReached) display with `[W]` prefix.
  - Each item: `"  [W] {description}"` or `"  [S] {description}"` — truncate description at 100 characters.
  - Show at most 5 items. If more than 5: append `"  ...and {N} more"`
- **Feedback section (when `reviewerNotes[]` is empty):** `"All reviewer issues resolved."`

### Step 3b: Forward Re-Run Check

After Step 3 (Phase Summary) completes:

1. Read entity metadata for `backward_return_target`
2. If `backward_return_target` exists AND `backward_return_target != current_phase`:
   a. Determine `next_phase` = phase after `current_phase` in PHASE_SEQUENCE
   b. Clear `backward_context` from entity metadata (already consumed by this phase)
   c. Output: "Forward re-run: {current_phase} → {next_phase} (returning to {backward_return_target})"
   d. Continue to /pd:{next_phase} [YOLO_MODE] — reuses the existing YOLO auto-chain mechanism
3. If `backward_return_target == current_phase`:
   a. Clear `backward_return_target` from entity metadata via `update_entity(type_id, metadata={"backward_return_target": null})`
   b. Output: "Reached backward return target. Resuming normal flow."
   c. Proceed to normal completion (standard auto-chain to next phase)
4. If `backward_return_target` does NOT exist:
   Normal flow (standard auto-chain)

## handleReviewerResponse

**Purpose:** Process a reviewer's response, handling backward travel if recommended. This is a shared procedure called by all phase commands after parsing a reviewer's response.

**Input:** reviewer_response (parsed JSON), feature_type_id, current_phase
**Output:** action = "approve" | "iterate" | "backward"

**Logic:**

1. If `reviewer_response.backward_to` exists:
   a. Validate `backward_to` is a valid phase earlier than `current_phase` in PHASE_SEQUENCE
   b. Store `backward_context` in entity metadata via `update_entity` MCP:
      ```
      update_entity(type_id=feature_type_id, metadata={
        "backward_context": reviewer_response.backward_context,
        "backward_return_target": current_phase
      })
      ```
   c. Update `backward_transition_reason` in workflow_phases (existing DB column):
      ```
      transition_phase(feature_type_id, reviewer_response.backward_to)
      ```
   d. Append to `backward_history` array in entity metadata:
      ```
      update_entity(type_id=feature_type_id, metadata={
        "backward_history": [...existing, {
          "source_phase": current_phase,
          "target_phase": reviewer_response.backward_to,
          "reason": reviewer_response.backward_reason,
          "timestamp": ISO_NOW,
          "issue_count": len(reviewer_response.issues)
        }]
      })
      ```
   e. **Ping-pong detection:**
      - Read `backward_history` from entity metadata
      - Filter entries with same (source_phase, target_phase) pair
      - If >= 2 previous entries exist AND current issue_count >= most recent previous entry's issue_count:
        - Ping-pong detected
        - YOLO: force approve with warnings, log "ping-pong detected, forcing forward"
        - Interactive: prompt "Same issues recurring. Force approve or continue?"
        - Return "approve"
   f. YOLO mode: output "Continue to /pd:{backward_to} [YOLO_MODE]"
      Interactive: prompt "Reviewer recommends going back to {backward_to}. Proceed?"
   g. Return "backward"

2. If `reviewer_response.approved == true` AND zero issues with severity "blocker" or "warning":
   Return "approve"

3. Else:
   Return "iterate"
