# Design: Branch-Based Development & Retro Before Cleanup

## Architecture Overview

This design covers two interconnected changes:
1. **Schema change**: Replace `worktree` field with `branch` in `.meta.json`
2. **Workflow change**: Run retrospective before branch cleanup in `/finish`

Both changes affect the same files and share common patterns.

---

## Component 1: .meta.json Schema

### Current Schema

```json
{
  "id": "006",
  "name": "retro-before-cleanup",
  "mode": "full",
  "status": "active",
  "created": "2026-01-30T00:00:00Z",
  "completed": null,
  "worktree": "../my-ai-setup-006-retro-before-cleanup",
  "currentPhase": "design",
  "phases": { ... }
}
```

### New Schema

```json
{
  "id": "006",
  "name": "retro-before-cleanup",
  "mode": "full",
  "status": "active",
  "created": "2026-01-30T00:00:00Z",
  "completed": null,
  "branch": "feature/006-retro-before-cleanup",
  "currentPhase": "design",
  "phases": { ... }
}
```

### Key Differences

| Field | Old | New |
|-------|-----|-----|
| `worktree` | `"../project-{id}-{slug}"` (path) | **REMOVED** |
| `branch` | N/A | `"feature/{id}-{slug}"` (branch name) |

### Backward Compatibility

During migration, existing `.meta.json` files may have `worktree` field. The hook and commands should:
1. Check for `branch` field first
2. If not present, check for `worktree` field and extract branch from it
3. Log a warning suggesting migration

```bash
# Fallback logic (pseudocode)
branch=$(jq -r '.branch // empty' "$meta_file")
if [[ -z "$branch" ]]; then
  worktree=$(jq -r '.worktree // empty' "$meta_file")
  if [[ -n "$worktree" ]]; then
    # Extract branch from worktree path
    # ../my-ai-setup-006-slug -> feature/006-slug
    branch="feature/$(basename "$worktree" | sed 's/^[^-]*-//')"
  fi
fi
```

---

## Component 2: Branch Check Pattern

### Shared Pattern

All phase commands (`/specify`, `/design`, `/create-plan`, `/create-tasks`, `/implement`, `/verify`) use the same worktree check pattern. Replace with a shared branch check pattern.

### Current Pattern (commands/*.md)

```markdown
### 1b. Check Worktree Location

If feature has a worktree defined in `.meta.json`:
- Compare current working directory against worktree path
- If mismatch and not already warned this session:
  ```
  ⚠️ You are not in the feature worktree.
  Current: {cwd}
  Worktree: {worktree}
  Continue anyway? (y/n)
  ```
- Skip this check if worktree is null (Hotfix mode)
```

### New Pattern (commands/*.md)

```markdown
### 1b. Check Branch

If feature has a branch defined in `.meta.json`:
- Get current branch: `git branch --show-current`
- If current branch != expected branch:
  ```
  ⚠️ You're on branch '{current}', but feature uses '{expected}'.

  Switch branches:
    git checkout {expected}

  Or continue on current branch? (y/n)
  ```
- Skip this check if branch is null (legacy or Hotfix mode)
```

### Files Using This Pattern

| File | Section to Update |
|------|-------------------|
| `commands/verify.md` | Section "1b. Check Worktree Location" |
| `commands/implement.md` | Section "1b. Check Worktree Location" |
| `commands/specify.md` | Section "1b. Check Worktree Location" |
| `commands/design.md` | Section "1b. Check Worktree Location" |
| `commands/create-plan.md` | Section "1b. Check Worktree Location" |
| `commands/create-tasks.md` | Section "1b. Check Worktree Location" |

---

## Component 3: Session Start Hook

### Current Logic (`hooks/session-start.sh`)

```
find_active_feature()
  → parse_feature_meta() extracts id, name, mode, worktree
  → check_worktree_mismatch() compares cwd with worktree path
  → build_context() adds warning if mismatch
```

### New Logic

```
find_active_feature()
  → parse_feature_meta() extracts id, name, mode, branch
  → check_branch_mismatch() compares current branch with expected
  → build_context() adds warning if mismatch
```

### Implementation Changes

#### 1. Update `parse_feature_meta()`

```bash
# Current (line ~65-74)
python3 -c "
import json
with open('$meta_file') as f:
    meta = json.load(f)
    print(meta.get('id', 'unknown'))
    print(meta.get('name', 'unknown'))
    print(meta.get('mode', 'Standard'))
    print(meta.get('worktree', ''))
"

# New
python3 -c "
import json
import os
with open('$meta_file') as f:
    meta = json.load(f)
    print(meta.get('id', 'unknown'))
    print(meta.get('name', 'unknown'))
    print(meta.get('mode', 'Standard'))
    # Prefer branch, fallback to extracting from worktree
    branch = meta.get('branch', '')
    if not branch and meta.get('worktree'):
        # Extract from worktree path: ../project-006-slug -> feature/006-slug
        wt = os.path.basename(meta.get('worktree', ''))
        parts = wt.split('-', 1)
        if len(parts) > 1:
            branch = f'feature/{parts[1]}'
    print(branch)
"
```

#### 2. Replace `check_worktree_mismatch()` with `check_branch_mismatch()`

```bash
# New function
check_branch_mismatch() {
    local expected_branch="$1"

    # Skip check if no branch defined
    if [[ -z "$expected_branch" ]]; then
        return 1
    fi

    # Get current branch
    local current_branch
    current_branch=$(git branch --show-current 2>/dev/null) || return 1

    # Compare
    if [[ "$current_branch" != "$expected_branch" ]]; then
        return 0  # Mismatch
    fi

    return 1  # Match
}
```

#### 3. Update `build_context()` warning message

```bash
# Current warning (lines ~166-170)
context+="\n⚠️  WARNING: You are not in the feature worktree.\n"
context+="   Current directory: ${cwd}\n"
context+="   Feature worktree: ${worktree}\n"
context+="   Consider: cd ${worktree}\n"

# New warning
current_branch=$(git branch --show-current 2>/dev/null)
context+="\n⚠️  You're on branch '${current_branch}', feature uses '${branch}'.\n"
context+="   Run: git checkout ${branch}\n"
```

---

## Component 4: Feature Creation

### Current Flow (`commands/create-feature.md`)

```
1. Get description, determine ID, create slug
2. Create docs/features/{id}-{slug}/
3. Based on mode:
   - Hotfix: worktree = null
   - Quick: ask user, maybe create worktree
   - Standard/Full: auto-create worktree
4. Create .meta.json with worktree path
5. Continue to /specify
```

### New Flow

```
1. Get description, determine ID, create slug
2. Create docs/features/{id}-{slug}/
3. Create branch: git checkout -b feature/{id}-{slug}
4. Create .meta.json with branch name
5. Continue to /specify
```

Mode no longer affects isolation strategy - all modes create a branch.

### Branch Creation Commands

```bash
# Create and switch to feature branch
git checkout -b feature/{id}-{slug}
```

---

## Component 5: Brainstorming Promotion

### Current Flow (`skills/brainstorming/SKILL.md`)

The promotion flow (lines ~68-114) has mode-based worktree logic:
- Hotfix: `"worktree": null`
- Quick: Ask user about worktree
- Standard/Full: Auto-create worktree

### New Flow

Remove all mode-based worktree decisions. Single path:

```markdown
**If yes (turn into feature):**
1. Ask for workflow mode (affects review iterations, not isolation)
2. Generate feature ID
3. Create folder: `docs/dev_artifacts/workitems/{id}-{slug}/`
4. Create branch: `git checkout -b feature/{id}-{slug}`
5. Move scratch file to feature folder as `brainstorm.md`
6. Create `.meta.json`:
   ```json
   {
     "id": "{id}",
     "name": "{slug}",
     "mode": "{selected-mode}",
     "created": "{ISO timestamp}",
     "branch": "feature/{id}-{slug}"
   }
   ```
7. Inform user: "Feature {id}-{slug} created on branch feature/{id}-{slug}."
8. Auto-invoke `/specify`
```

---

## Component 6: /finish Command Reordering

### Current Flow

```
Pre-completion checks
  ↓
Completion choice (PR/Merge/Keep/Discard)
  ↓
Execute choice
  ↓
Update .meta.json
  ↓
Delete .review-history.md
  ↓
Worktree cleanup
  ↓
Suggest retrospective  ← TOO LATE
```

### New Flow

```
Pre-completion checks
  ↓
Completion choice (PR/Merge/Keep/Discard)
  ↓
If "Keep": exit early
  ↓
Execute choice (PR/Merge/Discard only)
  ↓
RETROSPECTIVE (required)  ← MOVED HERE
  ├── Invoke retrospecting skill
  ├── User selects learnings
  └── Save retro.md
  ↓
Commit retro artifacts
  ↓
Update .meta.json
  ↓
Delete .review-history.md
  ↓
Branch cleanup (git branch -d/-D)
```

### Retro Timing Rationale

Running retro after merge but before branch deletion:
- Merge is done, so we know what went into main
- Branch still exists, so `git diff main...feature/xxx` still works
- Feature folder still has all artifacts for context

---

## Component 7: Finishing Branch Skill

### Current Flow (`skills/finishing-branch/SKILL.md`)

Step 4 includes worktree cleanup:
```bash
git worktree remove <worktree-path>
```

### New Flow

Remove worktree cleanup, keep branch deletion:
```bash
# After merge (option 1)
git branch -d <feature-branch>

# After discard (option 4)
git branch -D <feature-branch>
```

---

## Component 8: List Features Command

### Current Output

```
ID   Name         Phase      Worktree                        Last Activity
006  retro        design     ../my-ai-setup-006-retro        30 min ago
```

### New Output

```
ID   Name         Phase      Branch                          Last Activity
006  retro        design     feature/006-retro               30 min ago
```

### Implementation

Change column header and data source:
- Header: "Worktree" → "Branch"
- Data: Read `.branch` from `.meta.json` instead of `.worktree`

---

## Component 9: Show Status Command

### Current Detection Logic

```markdown
1. If argument provided: Use that feature ID
2. If in worktree: Extract feature ID from branch name
3. Otherwise: List recent features and ask
```

### New Detection Logic

```markdown
1. If argument provided: Use that feature ID
2. If on feature branch: Extract feature ID from branch name pattern `feature/{id}-{slug}`
3. Otherwise: List recent features and ask
```

### Branch Name Parsing

```bash
current_branch=$(git branch --show-current)
if [[ "$current_branch" =~ ^feature/([0-9]+)- ]]; then
    feature_id="${BASH_REMATCH[1]}"
fi
```

---

## Files to Delete

| File | Reason |
|------|--------|
| `skills/using-git-worktrees/SKILL.md` | Entire skill is worktree-specific |

---

## Pre-commit Guard Hook

After review, `hooks/pre-commit-guard.sh` requires **no changes**:
- The "worktree-aware" comment refers to handling directory context in commands
- It checks branch names, not worktree paths
- Works correctly for branch-based workflow

Optional: Update comment from "worktree-aware" to "directory-context-aware" for clarity.

---

## Migration Path

For existing features with `worktree` field:

1. **Backward-compatible reading**: Hook and commands check `branch` first, fall back to extracting from `worktree`
2. **Manual cleanup**: Users remove worktrees with `git worktree remove`
3. **Schema update**: Edit `.meta.json` to replace `worktree` with `branch`

No automated migration - the manual steps are documented in spec.md.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Existing worktrees orphaned | Medium | Low | Document cleanup steps |
| Branch name parsing fails | Low | Medium | Fallback to manual ID entry |
| Retro artifacts lost on failure | Low | Medium | Commit retro before cleanup |
| Users expect worktrees | Low | Low | Clear documentation |

---

## Dependencies

```
                    ┌─────────────────────┐
                    │  .meta.json schema  │
                    │  (branch field)     │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ session-start.sh │ │ Phase commands  │ │ /create-feature │
│ (branch check)   │ │ (branch check)  │ │ (branch create) │
└──────────────────┘ └─────────────────┘ └─────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ /finish             │
                    │ (retro + cleanup)   │
                    └─────────────────────┘
```

Implementation order:
1. Schema definition (this design)
2. Hook update (affects all sessions)
3. Commands update (can be done in parallel)
4. Skill updates
5. Documentation
6. Delete worktree skill

---

## Interface Contracts

### .meta.json Reader

```typescript
interface FeatureMeta {
  id: string;
  name: string;
  mode: 'hotfix' | 'quick' | 'standard' | 'full';
  status: 'active' | 'completed' | 'abandoned';
  created: string;  // ISO timestamp
  completed: string | null;
  branch: string;   // e.g., "feature/006-retro-before-cleanup"
  currentPhase: string;
  phases: Record<string, PhaseState>;
}

// Backward compatibility
function getBranch(meta: FeatureMeta | LegacyMeta): string {
  if (meta.branch) return meta.branch;
  if (meta.worktree) {
    // ../project-006-slug -> feature/006-slug
    const basename = path.basename(meta.worktree);
    const match = basename.match(/^[^-]+-(.+)$/);
    return match ? `feature/${match[1]}` : '';
  }
  return '';
}
```

### Branch Check Function

```typescript
function checkBranchMismatch(expectedBranch: string): {
  mismatch: boolean;
  currentBranch: string;
  message: string;
} {
  if (!expectedBranch) {
    return { mismatch: false, currentBranch: '', message: '' };
  }

  const current = execSync('git branch --show-current').toString().trim();

  if (current !== expectedBranch) {
    return {
      mismatch: true,
      currentBranch: current,
      message: `You're on '${current}', feature uses '${expectedBranch}'.\nRun: git checkout ${expectedBranch}`
    };
  }

  return { mismatch: false, currentBranch: current, message: '' };
}
```
