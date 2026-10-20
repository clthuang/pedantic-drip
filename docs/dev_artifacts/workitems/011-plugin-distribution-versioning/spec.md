# Specification: Plugin Distribution & Versioning

## Problem Statement

The iflow plugin lacks version control and public distribution, making it risky for personal use (breaking changes) and impossible for others to install.

## Success Criteria

- [ ] Feature branches merge to `develop` instead of `main`
- [ ] Release script calculates version from conventional commits and creates tagged release
- [ ] Local development uses `iflow-dev` plugin, leaving `iflow` available for stable version
- [ ] Public users can install via `/plugin marketplace add {owner}/my-ai-setup`

## Scope

### In Scope

1. **Branch restructure**: Create `develop` branch, update iflow workflow to target develop
2. **Release script**: Bash script that calculates version, updates files, tags, merges to main
3. **Dual plugin setup**: Rename local plugin to `iflow-dev`, update local marketplace
4. **Public marketplace**: Create marketplace.json for GitHub distribution

### Out of Scope

- CI/CD pipeline (manual release is sufficient)
- Changelog generation
- Multiple marketplace support
- npm or other package registry distribution

## Acceptance Criteria

### Branch Structure
- Given the repo has only `main` branch
- When `develop` branch is created and set as default
- Then `main` contains only tagged releases, `develop` is working branch

### Release Process
- Given commits on develop follow conventional format (feat:, fix:, BREAKING CHANGE:)
- When running `./scripts/release.sh`
- Then version is calculated, plugin.json and marketplace.json updated, git tag created, develop merged to main, pushed to remote

### Release Error Handling
- Given commits on develop have no conventional prefixes
- When running `./scripts/release.sh`
- Then script fails with error message explaining no version bump detected

### Local Development
- Given plugin renamed to `iflow-dev` in `.claude-plugin/marketplace.json`
- When Claude Code starts in my-ai-setup project
- Then `iflow-dev` commands are available from local source

### Public Distribution
- Given marketplace.json exists on main branch at `.claude-plugin/marketplace.json`
- When user runs `/plugin marketplace add {owner}/my-ai-setup`
- Then iflow plugin installs from latest release

## Dependencies

- GitHub repository must be public for distribution
- Claude Code plugin system (marketplace.json format)

## Open Questions

- Repo rename from `my-ai-setup` → deferred (not blocking, can do later)
