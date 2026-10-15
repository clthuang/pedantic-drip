---
last-updated: 2026-10-15T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Contributing

How to work on pedantic-drip: branching model, commit conventions, merging and releasing.

## Branch Model

| Branch | Purpose |
|--------|---------|
| `main` | Stable releases only (tagged versions) |
| `develop` | Integration branch — all feature work merges here |
| `feature/<id>` | Feature branches; `<id>` is the feature's `YYYY-MM-DD-slug` |
| `pd/<id>/task-<n>` | One plan task's branch inside `implement-tasks`; the merger lands it on `feature/<id>` |

**Always merge to `develop`, never directly to `main`.** The release script promotes `develop → main`.

## Starting a Feature

```
/pd:create-feature "<title>"
```

`pd-new feature` creates `docs/dev_artifacts/features/<id>/` with `README.md` and `log.md`; the command then branches `feature/<id>` from the base branch and commits the item.

## Commit Conventions

Use conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`; `BREAKING CHANGE:` in the body). The release script sizes the version bump from code change volume, not from the prefixes. Inside a pd workflow, phase commits are `<phase>: <summary>`.

> pd is private tooling with no external users — no backward compatibility. Delete old code; don't keep shims.

## Checks Before Committing

- **`./validate.sh`** — component validation; 0 errors expected.
- **`pd-commit-lint`** (PreToolUse hook) — runs `pd-lint --staged` before a `git commit` in an adopted project; an error blocks the commit. Fix it, never bypass it.
- **`pre-commit-guard`** — warns on commits to `main`/`master`.

## Finishing a Feature

```
/pd:finish-feature
```

It runs the security review, docs, the `metrics` entry and the retro check, then merges to `develop` and cleans up the branches. A retro, when one is owed, runs before cleanup: the branches are its input.

## PR Process

Solo work merges through `/pd:finish-feature`. For collaborative changes, push the feature branch, open a PR against `develop`, run `./validate.sh`, and merge after review.

## Releasing

See [README_FOR_DEV.md](../../README_FOR_DEV.md) ("Release Process", "Version Bump Logic"). In short: `bash scripts/release.sh --ci` on a clean `develop` with entries under `[Unreleased]` in `CHANGELOG.md`; `BUMP_OVERRIDE=patch|minor|major` forces the bump.

## Adding Components

New plugin components go in `plugins/pd/`. After adding, removing or renaming a skill, agent, command or hook, update the count and reference tables in `README.md`, `README_FOR_DEV.md` and `plugins/pd/README.md`; `scripts/check-doc-drift.sh` checks them. See the [Component Authoring Guide](../dev_guides/component-authoring.md).
