---
name: updating-docs
description: Documentation sync checklist for plugin component changes, publishing artifacts to the human docs, and the doc-writer dispatch. Use when adding, removing, or renaming a skill, command, agent, or hook, or when an artifact becomes reference material.
---

# Updating Docs

## Component sync checklist
Adding, removing, or renaming a plugin component means updating each line below in the same change. These counts and tables have drifted silently across past features; walk the list rather than guessing which entries moved.

- **Repo `README.md`** — skill, agent, and command tables plus their headline counts.
- **Repo `README_FOR_DEV.md`** — the same tables and counts, plus the hooks table when a hook is added or removed.
- **Plugin `README.md`** — component-count table and the command and agent tables.
- **Plugin `commands/secretary.md`** — the specialist fast-path table, when an agent listed there is renamed.
- **Repo `CHANGELOG.md`** — an entry under `## [Unreleased]` for user-visible changes only: new commands, skills, config options, behavior changes. Refactors, tests, and internal cleanups get no entry.

Verify each count by listing the files it claims to describe. Never adjust the previous number by hand.

## Publishing a development artifact
When an artifact under `{pd_artifacts_root}` becomes reference material (a design that settles how a subsystem works), write the human doc in `docs/technical/` (a lasting architecture decision: an ADR in `docs/technical/decisions/`). The artifact stays where it is; the human doc links to it. Write markdown per `${CLAUDE_PLUGIN_ROOT}/references/doc-format.md`, and read it as HTML with `uv run ${CLAUDE_PLUGIN_ROOT}/scripts/pd-html.py <file> --open`; generated HTML is never committed.

## Project documentation
For user-facing documentation beyond the checklist, dispatch `pd:documentation-researcher` to find which documents the change touches, then `pd:documentation-writer` to write them. Each dispatch carries the content of `${CLAUDE_PLUGIN_ROOT}/references/doc-schema.md` and, when `/pd:generate-docs` started this pass, its mode and each tier's last source-commit timestamp. The researcher's report names the affected tier; one writer dispatch per tier, run sequentially.

Skip both dispatches when the change has no user-visible surface — this pass advises, it never blocks.
