---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# API Reference

The command-line interfaces of pd's scripts, in `plugins/pd/scripts/`. Each usage below is the script's own docstring, minus its `--self-test` line: every script except `phase-gate.sh` (tested by `test-phase-gate.sh`) takes `--self-test`. Skills call them as `${CLAUDE_PLUGIN_ROOT}/scripts/<name>`.

## pd-new — create an item

```
pd-new <workitem|plan|brainstorm|rca> "<title>" [--from <path under the artifacts root | backlog#<id>>]
       [--mode standard|small|express]                       (--mode: work items only)
pd-new workitem --plan <plan id or path> <slug> "<title>"     (fills that roadmap's `planned: <slug>`)
pd-new backlog "<title>" [--from workitems/<id>]
```

Ids are local `YYYY-MM-DD-slug`. Inside a `/goal` run the conductor sets `PD_GOAL_RUN=1`, so a `tracker: github` item records `issue: pending` instead of publishing an issue.

## pd-status — the repository's state

```
pd-status              # print the state
```

Read-only, caches nothing. Prints the items by status and phase (an active plan reads `done` once its roadmap is), each roadmap's progress and next ready item, open blockers, cap stops answered, open assumptions, on-behalf decisions and done work items owing a retro. Takes no other argument.

## phase-gate.sh — a phase's exit check

```
phase-gate.sh <phase> <workitem-dir> [--express]
  phase ∈ specify|design|create-plan|implement|verify|finish|express
```

Checks artifacts, sections, the design's diagram and test strategy, duplicate contract blocks, and the `log.md` entries the phase owes. `express` is the mini-spec check (one task block in `shape.md` `## Requirements`), which replaces specify, design and create-plan for a `mode: express` work item. Exit 0 passes and prints `GATE PASS [<phase>] <workitem-dir>`; 1 prints each failure on its own line (`GATE FAIL [<phase>]: …`); 2 is a usage error.

## pd-lint — the artifact checks

```
pd-lint [<path>…]            every item under the artifacts root, or only the items the paths touch
pd-lint --staged             the commit hook's mode: the items `git diff --cached` touches
pd-lint --isolation <range>  test isolation over a diff (source/test/fixture paths)
pd-lint --risk <range>       risk signals over a diff (references/risk-patterns.md); warns only
pd-lint --archive            move ticked backlog lines into backlog-archive.md
pd-lint --sweep              list agent_sandbox/ dirs to clean; never deletes
```

Errors print `pd-lint: ERROR <path>:<line>: <message>` and exit 1; warnings never change the exit.

- **Not adopted:** in an old-layout project (`docs/features/` without `sop: 1`), every mode except `--self-test` prints `pd-lint: not adopted: run /pd:adopt` and exits 0.
- **`--staged` and unstaged changes:** a staged item with unstaged or untracked changes is an error, so the lint checks exactly what will be committed.

## pd-proof — judge a task's JUnit XML

```
pd-proof first <junit.xml>                         # the task's first (tests-only) commit
pd-proof head <junit.xml> [--first <junit.xml>]    # the task's HEAD
```

Prints one JSON result; exits 0 when ok, 1 when not, 2 on a usage error. Reads only the XML, never the console output. The `merger` agent is its caller.

## pd-review-filter — scope a re-review to the diff

```
pd-review-filter (--diff <file> | --range <A..B>) [<review.json>]    # the review from the file, or stdin
```

Prints the review JSON with `new_in_diff` cut to the findings whose file:line lies inside a hunk of the diff's new side, and names each dropped finding on stderr. Schema: `references/workflow-results.md`.

## pd-init — set a project up

```
pd-init [--force]          write .claude/pd.local.md, the artifacts root and three .gitignore lines,
                           then print the proposed .claude/settings.json diff without applying it
pd-init --apply-settings   write that proposed settings.json, once the user approved the diff
pd-init --decline          record this repository in ~/.claude/pd/init-declined ("never ask again")
```

Refuses an old-layout project (`docs/features/` without `sop: 1`): that one runs `pd-adopt`.

## pd-adopt — migrate an old-layout project, once

```
pd-adopt [--registry <path>] [--workspace <uuid>]          dry run: print the plan and the diff; change nothing
pd-adopt --apply [--registry <path>] [--workspace <uuid>]  on a new pd-adopt branch, one commit per step
```

Run it from the project root. The registry is opened once, read-only (`immutable=1`), to copy it into `agent_sandbox/<date>/pd-adopt/`; every later read uses the copy.

- **The registry:** `~/.claude/pd/entities/entities.db`, or `$ENTITY_DB_PATH`, unless `--registry` names one.
- **`--workspace`:** the registry workspace to read; by default, the one whose project root is this project.
- **A non-empty `-wal` file:** pd-adopt refuses to run, since `immutable=1` would skip it; checkpoint the registry first.
- **No registry:** pd-adopt takes the state from `.meta.json` alone.

## pd-html.py — markdown to HTML

```
uv run pd-html.py <file.md | dir> [--open]
uv run pd-html.py --all [--open]
```

Output goes to `<repo>/docs/_html/`, mirroring the source paths. Never commit it. `--all` renders `docs/user-guide/`, `docs/dev-guide/`, `docs/technical/` and every active item under the artifacts root (all of a work item's `.md` files; a plan, brainstorm or rca's one file).

## Shared formats

- **Log entries:** `plugins/pd/references/log-entries.md`.
- **Workflow results and the review schema:** `plugins/pd/references/workflow-results.md`.
- **The review call:** `plugins/pd/references/review-call.md`.
- **`.claude/pd.local.md` fields:** the proposed values `pd-init` writes come from its `render_config`; the read-time fallbacks for an unset field are `pd_common.CONFIG_DEFAULTS`.
