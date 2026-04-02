---
last-updated: 2026-04-02T10:30:00Z
source-feature: 075-phase-context-accumulation
---

<!-- AUTO-GENERATED: START - source: 075-phase-context-accumulation -->

# Contributing

How to work on pedantic-drip: branching model, commit conventions, PR process, and CI expectations.

## Branch Model

This repository uses a git-flow model:

| Branch | Purpose |
|--------|---------|
| `main` | Stable releases only (tagged versions) |
| `develop` | Integration branch — all feature work merges here |
| `feature/*` | Feature branches, created by the pd workflow |

**Always merge to `develop`, never directly to `main`.** The release script handles `develop → main` promotion with tagging.

## Starting a Feature

The pd workflow creates and manages feature branches automatically:

```
/pd:create-feature <name>
```

This creates `feature/{id}-{slug}`, registers the entity, initializes workflow state, and checks out the branch. Manual branch creation is discouraged — use the workflow so `.meta.json` and the entity registry stay consistent.

## Commit Conventions

Use conventional commits. The release script calculates the version bump from code change volume, not commit message prefixes — but conventional commits keep the log readable:

| Prefix | Use for |
|--------|---------|
| `feat:` | New user-visible behavior |
| `fix:` | Bug fixes |
| `refactor:` | Internal restructuring without behavior change |
| `test:` | Adding or updating tests |
| `docs:` | Documentation only |
| `chore:` | Tooling, CI, dependency updates |
| `BREAKING CHANGE:` | In the commit body, for incompatible changes |

> pd is private tooling with no external users — there is no backward compatibility requirement. Delete old code; do not maintain shims.

## Running Validation Before Committing

```bash
./validate.sh
```

The `pre-commit-guard` hook warns when committing to protected branches (`main`/`master`) and reminds about running tests. It does not block commits to `develop` or feature branches.

## Finishing a Feature

When implementation is complete and tests pass:

```
/pd:finish-feature
```

This runs the retrospective, updates the knowledge bank, commits remaining artifacts, and merges the feature branch to `develop`. Do not manually delete the feature branch before the retrospective runs — the retro reads `implementation-log.md` which lives on the branch.

## PR Process

For solo development the standard flow is `/pd:finish-feature` with the direct-merge option. For collaborative changes or significant refactors, open a PR against `develop`:

1. Push your feature branch
2. Open a PR targeting `develop`
3. Run `./validate.sh` locally and confirm it passes
4. Merge after review — squash merge is acceptable

## Release Process

Releases are triggered from `develop` once enough changes have accumulated:

**Option 1 — GitHub Actions (recommended):**

```bash
# Dry run first to verify what would happen
gh workflow run release.yml --ref develop -f dry_run=true

# Real release
gh workflow run release.yml --ref develop -f dry_run=false
```

**Option 2 — Local:**

```bash
# Must be on develop with a clean working tree
./scripts/release.sh
```

### Version Bump Logic

The release script calculates the bump automatically from code change volume since the last tag:

| Change % of total codebase | Bump |
|----------------------------|------|
| ≤ 3% | Patch (1.0.0 → 1.0.1) |
| 3–10% | Minor (1.0.0 → 1.1.0) |
| > 10% | Major (1.0.0 → 2.0.0) |

Use `BUMP_OVERRIDE=patch|minor|major` to force a specific bump type.

### What the Release Script Does

1. Validates preconditions (on `develop`, clean working tree, has remote origin)
2. Calculates version from code change percentage since last tag
3. Strips `-dev` suffix from `plugin.json` and `marketplace.json`
4. Promotes `CHANGELOG.md` `[Unreleased]` section to the new version
5. Commits on `develop`, pushes
6. Merges `develop → main` (no-ff), tags, pushes
7. Bumps `develop` to next `-dev` version

**Preconditions:** Clean working tree (git stash first if needed) and at least one entry under `[Unreleased]` in `CHANGELOG.md`.

## CI Expectations

The GitHub Actions release workflow validates the same conditions as `./validate.sh`. There is no separate CI pipeline for feature branches — local validation is the gate before merging.

## Adding Components

All new plugin components go in `plugins/pd/`. After adding, removing, or renaming a skill, agent, command, or hook, update the component count tables and reference tables in:

- `README.md` and `README_FOR_DEV.md`
- `plugins/pd/README.md`

See the [Component Authoring Guide](/docs/dev_guides/component-authoring.md) for templates and naming conventions.

<!-- AUTO-GENERATED: END -->
