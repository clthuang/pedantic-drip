# Plan: Plugin Distribution & Versioning

## Implementation Order

### Phase 1: Foundation (No Dependencies)

1. **Create develop branch** — Set up branch structure
   - Complexity: Simple
   - Files: None (git operations only)
   - Steps:
     - Create `develop` branch from current `main`
     - Push `develop` to remote
     - Set `develop` as default branch on GitHub

2. **Create initial version tag** — Baseline for version calculation
   - Complexity: Simple
   - Files: None (git operations only)
   - Steps:
     - Tag current main as `v1.0.0`
     - Push tag to remote

3. **Rename local plugin to iflow-dev** — Enable dual installation
   - Complexity: Simple
   - Files: `.claude-plugin/marketplace.json`
   - Steps:
     - Change plugin name from `iflow` to `iflow-dev`
     - Update marketplace name to `my-local-plugins`
     - Set version to `0.0.0-dev`

### Phase 2: Core Implementation

4. **Create release script** — Automate version calculation and release
   - Depends on: #1, #2
   - Complexity: Medium
   - Files: `scripts/release.sh`
   - Steps:
     - Validate preconditions (on develop, clean working tree)
     - Parse commits since last tag for conventional prefixes
     - Calculate version bump (major/minor/patch)
     - Update version in `plugins/iflow/.claude-plugin/plugin.json`
     - Update version in `.claude-plugin/marketplace.json`
     - Commit version changes
     - Merge develop → main
     - Create version tag
     - Push main and tags to remote

### Phase 3: Integration

5. **Create public marketplace on main** — Enable public installation
   - Depends on: #1, #4
   - Complexity: Simple
   - Files: `.claude-plugin/marketplace.json` (on main branch)
   - Steps:
     - On main branch, update marketplace.json:
       - name: `iflow-plugins`
       - plugin name: `iflow`
       - version: synced from plugin.json
     - This happens automatically via release script merge

6. **Update iflow workflow to target develop** — Feature branches merge to develop
   - Depends on: #1
   - Complexity: Medium
   - Files: `plugins/iflow/skills/finishing-branch/SKILL.md`
   - Steps:
     - Update default merge target from `main` to `develop`
     - Ensure /iflow:finish merges to develop, not main

## Dependency Graph

```
#1 Create develop ──────┬──→ #4 Release script ──→ #5 Public marketplace
        │               │
        │               │
#2 Initial tag ─────────┘

#3 Rename to iflow-dev (independent)

#6 Update iflow workflow ──→ depends on #1 only
```

## Risk Areas

- **Release script (#4)**: Most complex item. Version parsing from git log needs careful regex. Test with sample commits before running for real.
- **Branch switching during implementation**: This feature changes branch structure while we're implementing on a feature branch. Need to coordinate carefully.

## Testing Strategy

- **Release script**: Create test commits with different prefixes, verify version calculation
- **Local plugin**: Verify `iflow-dev` commands appear after marketplace rename
- **Public marketplace**: After first release, test `/plugin marketplace add` from a clean environment

## Definition of Done

- [ ] `develop` branch exists and is default on GitHub
- [ ] `v1.0.0` tag exists on main
- [ ] Local plugin renamed to `iflow-dev`
- [ ] Release script calculates version and creates releases
- [ ] Public users can install via `/plugin marketplace add`
- [ ] iflow workflow merges features to develop
