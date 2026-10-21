# Specification: Two-Plugin Coexistence

## Overview

Restructure the plugin organization from branch-based naming to two coexisting plugins:
- **iflow** — Production/stable (protected, updated via release script only)
- **iflow-dev** — Development (active work location)

This eliminates fragile branch-based transformations and provides clear separation.

---

## Requirements

### R1: Plugin Directory Structure

**R1.1** Create `plugins/iflow-dev/` directory with full plugin structure:
- `.claude-plugin/plugin.json` with `name: "iflow-dev"`
- All subdirectories: `skills/`, `commands/`, `hooks/`, `agents/`
- Copy current content from `plugins/iflow/`

**R1.2** Rename `plugins/iflow/.claude-plugin/plugin.json` name field to `"iflow"` (already correct)

**R1.3** Version scheme:
- `iflow-dev`: Next target version with `-dev` suffix (e.g., `1.2.0-dev`)
- `iflow`: Current release version (e.g., `1.1.0`)

### R2: Marketplace Configuration

**R2.1** Update `.claude-plugin/marketplace.json` to list both plugins:
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

**R2.2** Remove branch-based marketplace name switching (no more `iflow-plugins` vs `my-local-plugins`)

### R3: Release Script Updates

**R3.1** Rewrite `scripts/release.sh` for two-plugin model:
1. Validate preconditions (clean tree, on develop)
2. Calculate new version from conventional commits
3. Copy `plugins/iflow-dev/*` → `plugins/iflow/`
4. Update `plugins/iflow/.claude-plugin/plugin.json`:
   - Keep `name: "iflow"`
   - Set `version` to calculated release version (strip `-dev`)
5. Bump `plugins/iflow-dev/.claude-plugin/plugin.json`:
   - Keep `name: "iflow-dev"`
   - Set `version` to next minor with `-dev` suffix
6. Update `.claude-plugin/marketplace.json` with both new versions
7. Commit and push develop
8. Checkout main, merge develop (non-fast-forward: `--no-ff`), push
9. Create and push git tag
10. Return to develop

**R3.2** Remove marketplace format conversion functions:
- Delete `convert_to_public_marketplace()`
- Delete `convert_to_dev_marketplace()`

**R3.3** Set environment variable `IFLOW_RELEASE=1` during release for hook bypass

### R4: Hook Protection

**R4.1** Modify existing `plugins/iflow/hooks/pre-commit-guard.sh` to add protection:
- Existing behavior: Warn on commits to main/master (keep this)
- New behavior: Block commits that modify files in `plugins/iflow/` path
- Bypass if `IFLOW_RELEASE=1` environment variable is set
- Show clear error message directing user to edit `iflow-dev/` instead

**R4.2** The hook is already registered in `hooks.json`; no additional registration needed

**R4.3** After iflow-dev is created, the hook will exist in both plugins (as a copy); only `iflow-dev`'s hook runs during development since that's what's cached

### R5: Sync-Cache Script Updates

**R5.1** Update `plugins/iflow-dev/hooks/sync-cache.sh`:
- Sync `plugins/iflow-dev/` to cache (primary for development)
- Optionally sync `plugins/iflow/` to cache (for stable testing)
- Update marketplace.json in cache with both plugins

**R5.2** Handle both plugin entries in `installed_plugins.json` detection

### R6: Validate Script Updates

**R6.1** Update `validate.sh` to validate both plugins:
- Check `plugins/iflow/` structure
- Check `plugins/iflow-dev/` structure
- Validate version format (`X.Y.Z` for iflow, `X.Y.Z-dev` for iflow-dev)

### R7: Documentation Updates

**R7.1** Update `README.md`:
- Installation instructions for both plugins
- Clarify `iflow-dev` is for contributors/developers
- Clarify `iflow` is the stable release

**R7.2** Update `README_FOR_DEV.md`:
- Remove branch-based naming section
- Document two-plugin model
- Update release process documentation
- Document hook protection

**R7.3** Update `docs/dev_guides/component-authoring.md` if it references single plugin

---

## Acceptance Criteria

### AC1: Plugin Structure
- [ ] `plugins/iflow-dev/` exists with full content
- [ ] `plugins/iflow/` exists with current release content
- [ ] Both have valid `.claude-plugin/plugin.json`
- [ ] `iflow-dev` plugin.json has `name: "iflow-dev"` and version ending in `-dev`
- [ ] `iflow` plugin.json has `name: "iflow"` and release version

### AC2: Marketplace
- [ ] `.claude-plugin/marketplace.json` lists both plugins
- [ ] Both plugins installable via `/plugin install iflow@my-local-plugins` and `/plugin install iflow-dev@my-local-plugins`

### AC3: Commands Work
- [ ] `/iflow:show-status` works (production plugin)
- [ ] `/iflow-dev:show-status` works (dev plugin)
- [ ] Both show correct version in their output

### AC4: Release Script
- [ ] `./scripts/release.sh` copies iflow-dev → iflow
- [ ] Correctly bumps versions in both plugins
- [ ] Creates git tag
- [ ] No more marketplace format conversion

### AC5: Hook Protection
- [ ] Committing changes to `plugins/iflow/` is blocked with clear message
- [ ] Committing changes to `plugins/iflow-dev/` is allowed
- [ ] Release script can modify `plugins/iflow/` (bypass works)

### AC6: Sync-Cache
- [ ] Session start syncs `iflow-dev` to cache
- [ ] Marketplace cache updated with both plugins

### AC7: Validation
- [ ] `./validate.sh` passes
- [ ] Both plugins validated

### AC8: Documentation
- [ ] README.md reflects two-plugin model
- [ ] README_FOR_DEV.md updated with new workflow
- [ ] No references to branch-based naming transformation

---

## Out of Scope

- Public GitHub marketplace changes (handled separately)
- Migration of existing `iflow` users to `iflow-dev`
- Automated testing infrastructure

---

## Migration Notes

### For Feature 011 Branch
The `feature/011-plugin-distribution-versioning` branch has partial implementation of the old branch-based approach. That branch should be abandoned; this feature supersedes it.

### For Existing Users
After this change:
- Local development uses `iflow-dev` commands
- Public/stable users continue using `iflow` commands
- No change needed for public users

### Initial State After Implementation
- `iflow` version: `1.1.0` (current)
- `iflow-dev` version: `1.2.0-dev` (next target)
