---
last-updated: 2026-10-18T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Contributing

How to work on pedantic-drip: branching model, commit conventions, merging and releasing.

## Branch Model

| Branch | Purpose |
|--------|---------|
| `main` | Trunk and GitHub's default — all work lands here through PRs, merged as merge commits |
| `stable` | Release channel that installs follow; only the Publish workflow moves it, fast-forward only |
| `feature/<id>` | Feature branches; `<id>` is the feature's `YYYY-MM-DD-slug` |
| `pd/<id>/task-<n>` | One plan task's branch inside `implement-tasks`; the merger lands it on `feature/<id>` |
| `release/vX.Y.Z` | A release PR's branch, opened by `scripts/release-pr.sh` |

**Every change reaches `main` through a PR.** A ruleset requires it, with the `validate` check passing and up to date with `main`.

## Starting a Feature

```
/pd:create-feature "<title>"
```

`pd-new feature` creates `docs/features/<id>/` (this repo's `artifacts_root` is `docs`) with `README.md` and `log.md`; the command then branches `feature/<id>` from `main` and commits the item.

## Commit Conventions

Use conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`; `BREAKING CHANGE:` in the body). They don't set the version: the maintainer picks the bump at release time. Inside a pd workflow, phase commits are `<phase>: <summary>`.

> pd is private tooling with no external users — no backward compatibility. Delete old code; don't keep shims.

## Checks Before Committing

- **`./validate.sh`** — component validation; 0 errors expected.
- **`pd-commit-lint`** (PreToolUse hook) — runs `pd-lint --staged` before a `git commit` in an adopted project; an error blocks the commit. Fix it, never bypass it.
- **`pre-commit-guard`** — warns on commits to `main`/`master`.

## Finishing a Feature

```
/pd:finish-feature
```

It runs the security review, docs, the `metrics` entry and the retro check, then merges to `main` (here through a PR, as `main`'s ruleset requires) and cleans up the branches. A retro, when one is owed, runs before cleanup: the branches are its input.

## PR Process

Solo work merges through `/pd:finish-feature`. For collaborative changes, push the feature branch, open a PR against `main`, run `./validate.sh`, and merge after review. Add your entries under `## [Unreleased]` in `CHANGELOG.md`; released sections are frozen, and CI fails a PR that changes them.

## Releasing

See [README_FOR_DEV.md](../../README_FOR_DEV.md) ("Version", "Release Process"). In short: `scripts/release-pr.sh [patch|minor|major]` (default patch) on a clean `main` equal to `origin/main` opens the release PR; merge it once CI passes, and the Publish workflow tags `vX.Y.Z` and fast-forwards `stable`.

## Adding Components

New plugin components go in `plugins/pd/`. After adding, removing or renaming a skill, agent, command or hook, update the count and reference tables in `README.md`, `README_FOR_DEV.md` and `plugins/pd/README.md`; `scripts/check-doc-drift.sh` checks them. See the [Component Authoring Guide](../dev_guides/component-authoring.md).
