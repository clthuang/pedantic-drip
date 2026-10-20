# Tasks: Plugin Distribution & Versioning

## Task List

### Phase 1: Foundation

#### Task 1.1: Create develop branch from main
- **Files:** None (git operations)
- **Do:** Create `develop` branch from current `main` state
- **Test:** `git branch -a | grep develop`
- **Done when:** `develop` branch exists locally and on remote

#### Task 1.2: Set develop as default branch on GitHub
- **Files:** None (GitHub settings)
- **Do:** In GitHub repo settings, change default branch from `main` to `develop`
- **Test:** Check GitHub repo settings page
- **Done when:** GitHub shows `develop` as default branch

#### Task 1.3: Create v1.0.0 tag on main
- **Files:** None (git operations)
- **Do:** Tag current `main` as `v1.0.0` and push tag
- **Test:** `git tag -l | grep v1.0.0`
- **Done when:** `v1.0.0` tag exists and is pushed to remote

#### Task 1.4: Rename local plugin to iflow-dev
- **Files:** `.claude-plugin/marketplace.json`
- **Do:** Change plugin name to `iflow-dev`, marketplace name to `my-local-plugins`, version to `0.0.0-dev`
- **Test:** Start new Claude Code session, check for `iflow-dev` commands
- **Done when:** `/iflow-dev:show-status` command is available

### Phase 2: Core Implementation

#### Task 2.1: Create release script skeleton
- **Depends on:** Task 1.1, 1.3
- **Files:** `scripts/release.sh`
- **Do:** Create script with precondition checks (on develop, clean working tree, no uncommitted changes)
- **Test:** Run from wrong branch, verify it fails with clear message
- **Done when:** Script exits with error when preconditions fail

#### Task 2.2: Add version calculation logic
- **Depends on:** Task 2.1
- **Files:** `scripts/release.sh`
- **Do:** Parse git log since last tag for `feat:`, `fix:`, `BREAKING CHANGE:` prefixes; determine bump type
- **Test:** Create test commits with different prefixes, verify correct bump type
- **Done when:** Script outputs correct version bump type (major/minor/patch)

#### Task 2.3: Add file version updates
- **Depends on:** Task 2.2
- **Files:** `scripts/release.sh`
- **Do:** Update version in `plugins/iflow/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
- **Test:** Run script in dry-run mode, verify version changes
- **Done when:** Both JSON files show updated version after script runs

#### Task 2.4: Add git operations (commit, merge, tag, push)
- **Depends on:** Task 2.3
- **Files:** `scripts/release.sh`
- **Do:** Commit version changes, merge develop→main, create version tag, push all to remote
- **Test:** Run full release with a test commit
- **Done when:** New tag appears on main branch after script completes

### Phase 3: Integration

#### Task 3.1: Prepare public marketplace content for main
- **Depends on:** Task 1.1
- **Files:** `.claude-plugin/marketplace.json` (will be on main after merge)
- **Do:** During release script merge, ensure marketplace.json on main has `iflow` name and `iflow-plugins` marketplace name
- **Test:** After first release, check main branch marketplace.json
- **Done when:** Main branch has correct public marketplace configuration

#### Task 3.2: Update finishing-branch skill for develop target
- **Depends on:** Task 1.1
- **Files:** `plugins/iflow/skills/finishing-branch/SKILL.md`
- **Do:** Update default merge target from `main` to `develop`
- **Test:** Run `/iflow:finish` on a test branch, verify it merges to develop
- **Done when:** Feature branches merge to develop by default

#### Task 3.3: Verify end-to-end workflow
- **Depends on:** All previous tasks
- **Files:** None
- **Do:** Create test feature branch, make changes, finish to develop, run release script
- **Test:** Full workflow produces tagged release on main
- **Done when:** Complete cycle works from feature→develop→main with version tag

## Summary

- Total tasks: 11
- Phase 1: 4 tasks (foundation, no dependencies)
- Phase 2: 4 tasks (release script implementation)
- Phase 3: 3 tasks (integration and verification)
