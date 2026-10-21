# Design: Make Workflow Specs Executable

## Architecture Overview

Transform pseudocode in commands into executable instructions that Claude can follow.

**Two areas addressed:**
1. Executor-reviewer iteration loop (phase commands)
2. Worktree auto-creation (create-feature, brainstorm)

```
Current State:                    Target State:
┌─────────────────┐              ┌─────────────────┐
│ /specify        │              │ /specify        │
│                 │              │                 │
│ "Spawn          │    ───►      │ Use Task tool:  │
│  chain-reviewer"│              │   subagent_type:│
│ (pseudocode)    │              │   chain-reviewer│
│                 │              │   prompt: {...} │
└─────────────────┘              └─────────────────┘
```

## Components

### 1. Command Execution Instructions

**Purpose:** Replace pseudocode with explicit execution steps

**Files affected:**
- `commands/specify.md`
- `commands/design.md`
- `commands/create-plan.md`
- `commands/create-tasks.md`
- `commands/implement.md`

**Changes:**
- Add explicit Task tool call format for reviewer
- Add `--no-review` flag handling
- Add iteration state tracking instructions
- Add `.review-history.md` append format

### 2. Reviewer Invocation Format

**Purpose:** Define exact format for spawning chain-reviewer

**Location:** Inline in each command file (section: "Reviewer Invocation")

### 3. Flag Argument Support

**Purpose:** Allow `--no-review` to skip the loop

**Pattern:** Check for argument in command frontmatter, skip loop if present

## Interfaces

### Interface 1: Task Tool Call for Reviewer

```markdown
## Reviewer Invocation

To invoke the chain-reviewer, use the Task tool:

```
Task tool:
  subagent_type: chain-reviewer
  prompt: |
    Review the following artifacts for chain sufficiency.

    ## Previous Artifact ({previous_file})
    {previous_content or "None - this is the first phase"}

    ## Current Artifact ({current_file})
    {current_content}

    ## Next Phase Expectations
    {expectations_for_this_phase}

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [...],
      "summary": "..."
    }
```

The reviewer will return structured feedback. Parse the `approved` field to determine next action.
```

### Interface 2: Iteration Loop Instructions

```markdown
## Iteration Loop

Execute the following loop. The iteration counter is maintained in memory during command execution.

1. **Initialize:**
   - Set `iteration = 1`
   - Set `max` based on mode from .meta.json:
     - Hotfix: max = 1
     - Quick: max = 2
     - Standard: max = 3
     - Full: max = 5

2. **Execute skill:** Follow the specifying skill to produce spec.md

3. **Check for --no-review:** If flag present, skip to step 7

4. **Invoke reviewer:** Use Task tool as specified above

5. **Parse response:**
   - If reviewer response is not valid JSON: Ask reviewer to retry with correct format
   - Extract `approved` field from JSON response
   - If `approved: true` → Go to step 7
   - If `approved: false` AND iteration < max → Go to step 6
   - If `approved: false` AND iteration == max → Go to step 7 with concerns

6. **Revise:**
   - Append iteration to .review-history.md (format below)
   - Increment iteration: `iteration = iteration + 1`
   - Address reviewer issues by revising the artifact
   - Return to step 4

7. **Complete:** Update .meta.json (including final iteration count) and show completion message
```

### Interface 3: Review History Format

```markdown
## Review History Entry Format

Append to `.review-history.md`:

```markdown
## Iteration {n} - {ISO timestamp}

**Decision:** {Approved / Needs Revision}

**Issues:**
{For each issue:}
- [{severity}] {description} (at: {location})

**Changes Made:**
{Summary of revisions made to address issues}

---
```
```

### Interface 4: Flag Handling

```markdown
## Argument Handling

Check for `--no-review` flag:

```yaml
---
description: Create specification for current feature
argument-hint: [--no-review]
---
```

If `--no-review` is present in arguments:
- Skip the reviewer loop entirely
- Execute skill once
- Mark phase complete
- Note in .meta.json: `"reviewSkipped": true`
```

## Technical Decisions

### TD1: Inline vs Separate Skill for Loop

- **Choice:** Inline in each command
- **Alternatives:** Create `executing-with-review` skill that commands call
- **Rationale:** Commands already have the loop documented; adding another skill layer adds complexity. Inline is more direct and debuggable.

### TD2: Flag Syntax

- **Choice:** `--no-review` flag in command arguments
- **Alternatives:** Environment variable, mode-based auto-skip, config file
- **Rationale:** Explicit per-invocation control; matches common CLI patterns

### TD3: Review History Verbosity

- **Choice:** Full iteration details in `.review-history.md`
- **Alternatives:** Summary only, JSON format, omit entirely
- **Rationale:** Helps debugging and understanding why iterations happened; cleaned up on /finish anyway

### TD4: Reviewer Output Parsing

- **Choice:** Expect JSON in reviewer response, parse `approved` field
- **Alternatives:** Natural language parsing, structured tool output
- **Rationale:** chain-reviewer.md already specifies JSON output format; reliable parsing

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude doesn't follow loop | High - no iteration | Explicit step-by-step instructions with numbered steps |
| JSON parsing fails | Medium - stuck | Instruct to retry if malformed; provide example format |
| Reviewer returns unexpected format | Medium - parsing error | chain-reviewer.md has strict output format; validate |
| Too many iterations waste tokens | Medium - cost | Mode limits cap iterations; user can --no-review |

## Files to Modify

### Executor-Reviewer Loop

| Action | File | Changes |
|--------|------|---------|
| Modify | `commands/specify.md` | Add execution instructions, flag handling |
| Modify | `commands/design.md` | Add execution instructions, flag handling |
| Modify | `commands/create-plan.md` | Add execution instructions, flag handling |
| Modify | `commands/create-tasks.md` | Add execution instructions, flag handling |
| Modify | `commands/implement.md` | Add execution instructions, flag handling |

### Worktree Auto-Creation

| Action | File | Changes |
|--------|------|---------|
| Modify | `commands/create-feature.md` | Add worktree skill invocation |
| Modify | `skills/brainstorming/SKILL.md` | Add worktree in promotion flow |

## Examples by Command

Each command has different previous artifacts and next phase expectations. Below is the example for specify.md. During implementation, adapt for each command using this reference table:

| Command | Previous Artifact | Current Artifact | Next Phase Expectations |
|---------|------------------|------------------|------------------------|
| /specify | brainstorm.md (optional) | spec.md | "Design needs: All requirements listed, acceptance criteria defined, scope boundaries clear" |
| /design | spec.md | design.md | "Plan needs: Components defined, interfaces specified, dependencies identified, risks noted" |
| /create-plan | design.md | plan.md | "Tasks needs: Ordered steps with dependencies, all design items covered, clear sequencing" |
| /create-tasks | plan.md | tasks.md | "Implement needs: Small actionable tasks (<15 min each), clear acceptance criteria per task" |
| /implement | tasks.md | code changes | "Verify needs: All tasks addressed, tests exist/pass, no obvious issues" |

## Example: Updated specify.md Section

```markdown
### 4. Execute with Reviewer Loop

Get max iterations from mode: Hotfix=1, Quick=2, Standard=3, Full=5.

**If `--no-review` flag is present:** Skip to step 4e directly after producing artifact.

**Otherwise, execute this loop:**

a. **Produce artifact:** Follow the specifying skill to create/revise spec.md

b. **Invoke reviewer:** Use the Task tool to spawn chain-reviewer:
   ```
   Task tool call:
     subagent_type: chain-reviewer
     prompt: |
       Review the following artifacts for chain sufficiency.

       ## Previous Artifact (brainstorm.md)
       {content of brainstorm.md, or "None" if doesn't exist}

       ## Current Artifact (spec.md)
       {content of spec.md}

       ## Next Phase Expectations
       Design needs: All requirements listed, acceptance criteria defined,
       scope boundaries clear.

       Return your assessment as JSON.
   ```

c. **Parse response:** Extract the `approved` field from reviewer's JSON response.

d. **Branch on result:**
   - If `approved: true` → Proceed to step 4e
   - If `approved: false` AND iteration < max:
     - Append iteration to .review-history.md
     - Increment iteration counter
     - Address the issues by revising spec.md
     - Return to step 4b
   - If `approved: false` AND iteration == max:
     - Note concerns in .meta.json reviewerNotes
     - Proceed to step 4e

e. **Complete phase:** Update state and show completion message.
```

## Part 2: Worktree Auto-Creation

### Components

#### 1. Create-Feature Command Update

**File:** `commands/create-feature.md`

**Changes:**
- Add explicit invocation of `using-git-worktrees` skill
- Add mode-based decision logic
- Add worktree path storage in `.meta.json`

#### 2. Brainstorm Promotion Flow Update

**File:** `skills/brainstorming/SKILL.md`

**Changes:**
- Add explicit worktree creation step in promotion flow
- Same mode-based logic as create-feature

### Interface: Worktree Creation Instructions

```markdown
## Worktree Creation (after feature folder created)

Based on the selected mode:

**Hotfix mode:**
- Skip worktree creation entirely
- Set `.meta.json`: `"worktree": null`

**Quick mode:**
- Ask user: "Create isolated worktree for this feature? (y/n)"
- If user declines: Set `.meta.json`: `"worktree": null`
- If user confirms: Execute the same worktree creation steps as Standard/Full (below)

**Standard/Full mode:**
- Automatically create worktree (no user prompt)
- Worktree path: `../{project-name}-{feature-id}-{slug}`
- Branch name: `feature/{feature-id}-{slug}`
- Store in `.meta.json`: `"worktree": "../{path}"`

**Worktree Creation Steps (inline, not a separate skill call):**

Read the `using-git-worktrees` skill for reference, then execute these commands:

```bash
# 1. Verify we're in a git repository
git rev-parse --git-dir

# 2. Get project name from current directory
project_name=$(basename $(pwd))

# 3. Create worktree with new branch
git worktree add "../${project_name}-${feature_id}-${slug}" -b "feature/${feature_id}-${slug}"

# 4. Verify creation succeeded
ls -la "../${project_name}-${feature_id}-${slug}"
```

After successful creation:
- Store path in `.meta.json`: `"worktree": "../{project}-{id}-{slug}"`
- Inform user: "Worktree created at ../{path}. Consider: cd ../{path}"

If creation fails:
- Set `.meta.json`: `"worktree": null`
- Warn user: "Failed to create worktree: {error}. Continuing without isolation."
```

### Files to Modify (Worktree)

| Action | File | Changes |
|--------|------|---------|
| Modify | `commands/create-feature.md` | Add worktree creation instructions |
| Modify | `skills/brainstorming/SKILL.md` | Add worktree creation in promotion flow |

## Dependencies

- Existing chain-reviewer agent (already has correct output format)
- Existing using-git-worktrees skill (already complete)
- Task tool available in Claude Code
- Existing command files with pseudocode to replace
