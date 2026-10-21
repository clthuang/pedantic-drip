# Implementation Plan: Two-Plugin Coexistence

## Overview

Transform from branch-based plugin naming to two coexisting plugins (iflow + iflow-dev).

---

## Implementation Order

```
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 1: Foundation                                                  │
│ ┌─────────────┐                                                      │
│ │ 1. Create   │──┐                                                   │
│ │ iflow-dev/  │  │                                                   │
│ └─────────────┘  │                                                   │
│                  ▼                                                   │
│ ┌─────────────────────┐    ┌──────────────────────┐                 │
│ │ 2. Update           │───▶│ 3. Update            │                 │
│ │ iflow-dev/plugin.json│   │ marketplace.json     │                 │
│ └─────────────────────┘    └──────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 2: Hooks & Scripts                                             │
│ ┌──────────────────────┐    ┌──────────────────────┐                │
│ │ 4. Update            │    │ 5. Add protection    │                │
│ │ sync-cache.sh        │    │ pre-commit-guard.sh  │                │
│ └──────────────────────┘    └──────────────────────┘                │
│         │                            │                               │
│         └──────────┬─────────────────┘                               │
│                    ▼                                                 │
│           ┌──────────────────┐                                       │
│           │ 6. Rewrite       │                                       │
│           │ release.sh       │                                       │
│           └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 3: Validation & Documentation                                  │
│ ┌──────────────────────┐                                             │
│ │ 7. Update            │                                             │
│ │ validate.sh          │                                             │
│ └──────────────────────┘                                             │
│         │                                                            │
│         ▼                                                            │
│ ┌──────────────┐  ┌────────────────────┐  ┌────────────────────────┐│
│ │ 8. Update    │  │ 9. Update          │  │ 10. Check component-   ││
│ │ README.md    │  │ README_FOR_DEV.md  │  │     authoring.md       ││
│ └──────────────┘  └────────────────────┘  └────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Step Details

### Phase 1: Foundation

#### Step 1: Create iflow-dev directory
**Files:** `plugins/iflow-dev/` (entire directory)
**Action:** Copy `plugins/iflow/` → `plugins/iflow-dev/`
**Requirement:** R1.1
**Verification:** Directory exists with all subdirectories

```bash
cp -r plugins/iflow plugins/iflow-dev
```

#### Step 2: Update iflow-dev plugin.json
**File:** `plugins/iflow-dev/.claude-plugin/plugin.json`
**Action:**
- Change `name` from `"iflow"` to `"iflow-dev"`
- Change `version` from `"1.1.0"` to `"1.2.0-dev"`
**Requirement:** R1.1, R1.3
**Verification:** `jq '.name, .version' plugins/iflow-dev/.claude-plugin/plugin.json`

#### Step 3: Update marketplace.json
**File:** `.claude-plugin/marketplace.json`
**Action:** Add iflow plugin entry alongside iflow-dev
**Requirement:** R2.1
**Verification:** Both plugins listed in `jq '.plugins[].name'`

```json
{
  "name": "my-local-plugins",
  "plugins": [
    {
      "name": "iflow",
      "source": "./plugins/iflow",
      "version": "1.1.0"
    },
    {
      "name": "iflow-dev",
      "source": "./plugins/iflow-dev",
      "version": "1.2.0-dev"
    }
  ]
}
```

---

### Phase 2: Hooks & Scripts

#### Step 4: Update sync-cache.sh
**File:** `plugins/iflow-dev/hooks/sync-cache.sh`
**Action:**
- Change source path from `plugins/iflow` to `plugins/iflow-dev`
- Add detection for both plugins in installed_plugins.json
- Sync iflow-dev as primary
- Optionally sync iflow if installed
**Requirement:** R5.1, R5.2
**Verification:** Run `/iflow-dev:sync-cache`, check both synced

#### Step 5: Add protection to pre-commit-guard.sh
**File:** `plugins/iflow-dev/hooks/pre-commit-guard.sh`
**Action:**
- Add IFLOW_RELEASE bypass check at start
- Add check for `plugins/iflow/` in staged files
- Block with clear message if detected
**Requirement:** R4.1
**Verification:**
1. `touch plugins/iflow/test && git add . && git commit -m "test"` → blocked
2. `IFLOW_RELEASE=1 git commit` → allowed

#### Step 6: Rewrite release.sh
**File:** `scripts/release.sh`
**Action:**
- Remove `convert_to_public_marketplace()` function
- Remove `convert_to_dev_marketplace()` function
- Update copy logic: `iflow-dev/*` → `iflow/`
- Update version bumping for both plugins
- Add `IFLOW_RELEASE=1` to git commands
**Requirement:** R3.1, R3.2, R3.3
**Verification:** Dry-run release script logic (no actual push)

---

### Phase 3: Validation & Documentation

#### Step 7: Update validate.sh
**File:** `validate.sh`
**Action:**
- Add validation for `plugins/iflow-dev/` structure
- Add version format validation (X.Y.Z vs X.Y.Z-dev)
**Requirement:** R6.1
**Verification:** `./validate.sh` passes

#### Step 8: Update README.md
**File:** `README.md`
**Action:**
- Update installation instructions for both plugins
- Clarify iflow-dev for contributors, iflow for users
**Requirement:** R7.1
**Verification:** Instructions accurate

#### Step 9: Update README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Action:**
- Remove "Plugin Names" section about branch-based naming
- Document two-plugin model
- Update release process section
- Add hook protection documentation
**Requirement:** R7.2
**Verification:** No references to branch-based transformation

#### Step 10: Check component-authoring.md
**File:** `docs/dev_guides/component-authoring.md`
**Action:** Review for single-plugin references, update if needed
**Requirement:** R7.3
**Verification:** All paths reference iflow-dev for development

---

## Dependencies

| Step | Depends On | Reason |
|------|------------|--------|
| 2 | 1 | Can't update file until directory exists |
| 3 | 1 | Need iflow-dev to reference in marketplace |
| 4 | 1 | sync-cache needs iflow-dev path to exist |
| 5 | 1 | Hook will be in iflow-dev after copy |
| 6 | 4, 5 | Release script uses both hooks |
| 7 | 1, 2 | Validates iflow-dev structure and version |
| 8-10 | 1-7 | Docs describe completed implementation |

---

## Verification Checklist

After implementation, verify:

- [ ] `plugins/iflow-dev/` exists with full content
- [ ] `plugins/iflow-dev/.claude-plugin/plugin.json` has name="iflow-dev", version="1.2.0-dev"
- [ ] `plugins/iflow/.claude-plugin/plugin.json` has name="iflow", version="1.1.0"
- [ ] `.claude-plugin/marketplace.json` lists both plugins
- [ ] `/iflow-dev:show-status` works
- [ ] `/iflow:show-status` works (after installing iflow plugin)
- [ ] Committing to `plugins/iflow/` is blocked
- [ ] `IFLOW_RELEASE=1` bypasses protection
- [ ] `./validate.sh` passes
- [ ] `./scripts/release.sh --dry-run` works (if implemented)

---

## Notes

- Steps 1-3 form the critical foundation and must succeed before proceeding
- Steps 4-6 can be done in parallel after foundation is complete
- Steps 8-10 can be done in parallel after validation
- Feature 011 branch should be deleted after this feature completes
