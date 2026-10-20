---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Contributing

How to work on pedantic-drip: starting and finishing a work item, commit conventions, checks and PRs.

## Branches and Releases

[README_FOR_DEV.md](../../README_FOR_DEV.md) owns both:

- **Branch model and the `main` ruleset:** ["Branch Structure"](../../README_FOR_DEV.md#branch-structure).
- **Release steps:** ["Release Process"](../../README_FOR_DEV.md#release-process).

## Starting a Work Item

```
/pd:create-workitem "<title>"
```

`pd-new workitem` creates `{pd_artifacts_root}/workitems/<id>/` with `README.md` and `log.md`; the command then branches `workitem/<id>` from `main` and commits the item.

**This repo is adopted:** its `.claude/pd.local.md` sets `artifacts_root: docs/dev_artifacts` and `sop: 1`, so `pd-lint` checks every item.

## Commit Conventions

Use conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`; `BREAKING CHANGE:` in the body). They don't set the version: the maintainer picks the bump at release time. Inside a pd workflow, phase commits are `<phase>: <summary>`.

> pd is private tooling with no external users — no backward compatibility. Delete old code; don't keep shims.

## Checks Before Committing

- **`./validate.sh`** — component validation; 0 errors expected.
- **`pd-commit-lint`** (PreToolUse hook on Claude's Bash tool) — runs `pd-lint --staged` before each `git commit` Claude runs; commits you type in a terminal aren't checked. An error blocks the commit: fix it, never bypass it.
- **`pre-commit-guard`** (PreToolUse hook on Claude's Bash tool) — never blocks or approves a call. On a commit to `main`/`master`, or a commit in a project with test files, it adds a reminder to Claude's context.

## Finishing a Work Item

```
/pd:finish-workitem
```

It runs the security review, docs, the `metrics` entry and the retro check, then merges to `main` (here through a PR, as `main`'s ruleset requires) and cleans up the branches. A retro, when one is owed, runs before cleanup: the branches are its input.

## PR Process

Solo work merges through `/pd:finish-workitem`. For collaborative changes, push the work item's branch, open a PR against `main`, run `./validate.sh`, and merge after review. Add your entries under `## [Unreleased]` in `CHANGELOG.md`; released sections are frozen, and CI fails a PR that changes them.

## Adding Components

New plugin components go in `plugins/pd/`. After adding, removing or renaming a skill, agent, command or hook, update `README.md`, `README_FOR_DEV.md` and `plugins/pd/README.md`, plus the Specialist fast path table in `plugins/pd/commands/secretary.md` when an agent it lists changes. See the [Component Authoring Guide](component-authoring.md).

`scripts/check-doc-drift.sh` (run by `validate.sh`) checks only these:

- **Counts:** the Skills, Agents and Commands rows of `plugins/pd/README.md`'s Components table, and README.md's "N skills and M agents" sentence, against the filesystem.
- **Hooks:** each script `hooks.json` registers exists and its name appears in `README_FOR_DEV.md`; each `.sh` in `plugins/pd/hooks/` is registered.
- **Stale strings:** a short blocklist of retired names has no hits in the living docs.

**Sweep by hand:** the skill, agent and command tables and their descriptions, each hook's trigger and purpose in `README_FOR_DEV.md`, and the secretary table.
