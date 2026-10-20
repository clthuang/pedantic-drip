# Tasks: Two-Plugin Coexistence

## Phase 1: Foundation

### Task 1.1: Copy iflow directory to iflow-dev
**File:** `plugins/iflow-dev/`
**Action:** `cp -r plugins/iflow plugins/iflow-dev`
**Done when:** `ls plugins/iflow-dev/.claude-plugin/plugin.json` succeeds

---

### Task 1.2: Update iflow-dev plugin.json name
**File:** `plugins/iflow-dev/.claude-plugin/plugin.json`
**Action:** Change `"name": "iflow"` to `"name": "iflow-dev"`
**Done when:** `jq -r '.name' plugins/iflow-dev/.claude-plugin/plugin.json` outputs `iflow-dev`

---

### Task 1.3: Update iflow-dev plugin.json version
**File:** `plugins/iflow-dev/.claude-plugin/plugin.json`
**Action:** Change `"version": "1.1.0"` to `"version": "1.2.0-dev"`
**Done when:** `jq -r '.version' plugins/iflow-dev/.claude-plugin/plugin.json` outputs `1.2.0-dev`

---

### Task 1.4: Add iflow entry to marketplace.json
**File:** `.claude-plugin/marketplace.json`
**Action:** Add new plugin entry for iflow pointing to `./plugins/iflow` with version `1.1.0`
**Done when:** `jq '.plugins | length' .claude-plugin/marketplace.json` outputs `2`

---

### Task 1.5: Update iflow-dev entry in marketplace.json
**File:** `.claude-plugin/marketplace.json`
**Action:** Update iflow-dev source to `./plugins/iflow-dev`, version to `1.2.0-dev`
**Done when:** `jq '.plugins[] | select(.name=="iflow-dev") | .version' .claude-plugin/marketplace.json` outputs `1.2.0-dev`

---

## Phase 2: Hooks & Scripts

### Task 2.1: Update sync-cache.sh source path
**File:** `plugins/iflow-dev/hooks/sync-cache.sh`
**Action:** Change `SOURCE_PLUGIN` from `plugins/iflow` to `plugins/iflow-dev`
**Done when:** `grep 'plugins/iflow-dev' plugins/iflow-dev/hooks/sync-cache.sh` finds the path

---

### Task 2.2: Add iflow sync to sync-cache.sh
**File:** `plugins/iflow-dev/hooks/sync-cache.sh`
**Action:** Add optional sync for iflow plugin if installed in cache
**Done when:** `grep -q 'CACHE_IFLOW.*rsync' plugins/iflow-dev/hooks/sync-cache.sh` succeeds

---

### Task 2.3: Add IFLOW_RELEASE bypass to pre-commit-guard.sh
**File:** `plugins/iflow-dev/hooks/pre-commit-guard.sh`
**Action:** Add check at start of main(): if `IFLOW_RELEASE=1`, output_allow and exit
**Done when:** `grep 'IFLOW_RELEASE' plugins/iflow-dev/hooks/pre-commit-guard.sh` finds the check

---

### Task 2.4: Add iflow protection check to pre-commit-guard.sh
**File:** `plugins/iflow-dev/hooks/pre-commit-guard.sh`
**Action:** Add check for staged files in `plugins/iflow/` path, block with message
**Done when:** Script blocks commits touching plugins/iflow/ (unless bypass)

---

### Task 2.5: Remove convert_to_public_marketplace from release.sh
**File:** `scripts/release.sh`
**Action:** Delete the `convert_to_public_marketplace()` function and its call
**Done when:** `grep 'convert_to_public' scripts/release.sh` returns nothing

---

### Task 2.6: Remove convert_to_dev_marketplace from release.sh
**File:** `scripts/release.sh`
**Action:** Delete the `convert_to_dev_marketplace()` function and its call
**Done when:** `grep 'convert_to_dev' scripts/release.sh` returns nothing

---

### Task 2.7: Add copy iflow-dev to iflow in release.sh
**File:** `scripts/release.sh`
**Action:** Add `cp -r plugins/iflow-dev/* plugins/iflow/` in update section
**Done when:** `grep -q 'cp.*iflow-dev.*iflow' scripts/release.sh` succeeds

---

### Task 2.8: Update release.sh to set iflow plugin.json name
**File:** `scripts/release.sh`
**Action:** After copy, change `plugins/iflow/.claude-plugin/plugin.json` name to `"iflow"`
**Done when:** `grep -q 'sed.*iflow-dev.*iflow.*plugin.json' scripts/release.sh` succeeds

---

### Task 2.9: Update release.sh version bumping for both plugins
**File:** `scripts/release.sh`
**Action:** Update both plugin.json files with correct versions
**Done when:** `grep -q 'plugins/iflow-dev/.*version.*dev' scripts/release.sh` succeeds

---

### Task 2.10: Add IFLOW_RELEASE=1 to release.sh git commands
**File:** `scripts/release.sh`
**Action:** Prefix git add/commit with `IFLOW_RELEASE=1`
**Done when:** `grep 'IFLOW_RELEASE=1 git' scripts/release.sh` finds the commands

---

### Task 2.11: Update release.sh marketplace.json version updates
**File:** `scripts/release.sh`
**Action:** Update both plugin versions in marketplace.json
**Done when:** Both iflow and iflow-dev versions updated in marketplace

---

## Phase 3: Validation & Documentation

### Task 3.1: Add iflow-dev validation to validate.sh
**File:** `validate.sh`
**Action:** Add call to validate `plugins/iflow-dev/` structure
**Done when:** `./validate.sh` checks iflow-dev plugin

---

### Task 3.2: Add version format validation to validate.sh
**File:** `validate.sh`
**Action:** Add check for iflow-dev version ending in `-dev`, iflow version without
**Done when:** Validation fails if version format is wrong

---

### Task 3.3: Update README.md installation section
**File:** `README.md`
**Action:** Add instructions for both plugins (iflow for users, iflow-dev for contributors)
**Done when:** Both plugins documented with clear audience distinction

---

### Task 3.4: Remove branch-based naming from README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Action:** Remove "Plugin Names" section mentioning branch-based naming
**Done when:** No mention of `develop` branch = `iflow-dev` naming

---

### Task 3.5: Add two-plugin model to README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Action:** Document that iflow-dev is for development, iflow is production
**Done when:** Two-plugin model clearly explained

---

### Task 3.6: Update release process in README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Action:** Update to describe copy-based release (no branch transformation)
**Done when:** Release docs match new workflow

---

### Task 3.7: Add hook protection docs to README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Action:** Document that plugins/iflow/ is protected, use IFLOW_RELEASE=1 to bypass
**Done when:** Hook protection documented

---

### Task 3.8: Review component-authoring.md for updates
**File:** `docs/dev_guides/component-authoring.md`
**Action:** Search for `plugins/iflow/` paths and update to `plugins/iflow-dev/` for development instructions
**Done when:** `grep -c 'plugins/iflow/' docs/dev_guides/component-authoring.md` returns 0 or only references production plugin

---

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| Phase 1 | 1.1 - 1.5 | Create iflow-dev, update configs |
| Phase 2 | 2.1 - 2.11 | Hooks and release script |
| Phase 3 | 3.1 - 3.8 | Validation and documentation |

**Total:** 24 tasks
