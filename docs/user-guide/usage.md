---
last-updated: 2026-10-15T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
audit-feature: 098-tier-doc-frontmatter-sweep
---

# Usage

## Set a Project Up

```bash
/pd:init     # a new project: writes .claude/pd.local.md, proposes .claude/settings.json changes
/pd:adopt    # an old-layout pd project (docs/features/ without `sop: 1`): migrates it once
```

`/pd:init` proposes `worktree.baseRef: "head"` (task worktrees start from the feature branch), the spawn-depth cap and allow rules for unattended runs. Set `qa_battery` in `.claude/pd.local.md`: Verify needs it.

## Quick Start

`/pd:secretary` triages a request — feature (at a depth), brainstorm, RCA or specialist — states why, and routes:

```bash
/pd:secretary "add email validation to the signup form"
```

Or start directly:

```bash
/pd:brainstorm "your idea here"                          # Clarify: a PRD in brainstorms/<id>.md
/pd:root-cause-analysis "the export drops the last row"  # Clarify for a bug: rca/<id>.md
/pd:create-feature "add user auth"                       # a standard feature and its branch
/pd:create-feature "fix the pagination off-by-one" --mode express
```

## The Standard Workflow

```bash
/pd:specify        # shape.md ## Requirements: B-numbered expectations, calvin, your sign-off
/pd:design         # shape.md ## Design: diagram, contracts, test strategy → review call
/pd:create-plan    # plan.md: task blocks with test cases → test-case review
/pd:implement      # implement-tasks: one implementer per task, the merger lands each
/pd:verify         # verify-change: code review beside QA, then fix cycles
/pd:finish-feature # security review, docs, metrics, retro if owed, merge, cleanup
```

Each command invokes its stage skill. Before `phase:` moves on, `phase-gate.sh <phase>` must pass; every commit runs `pd-lint --staged`.

- **Small** (`--mode small`): design and plan are written in one sitting and reviewed in one joint call.
- **Express** (`--mode express`): `shape.md` holds a mini-spec with one task block; `/pd:implement` runs that one task and Verify is lighter.
- **Backward moves:** a wrong criterion or test case sends the feature back (`phase <from> -> <to> (back)` in `log.md`); merged tasks stay merged.

## Long Runs

Start a `/goal` run on a feature; the conductor writes `goal: <id> target <phase> session <id>` to the README's `## Now`. The Stop hook holds the run until the target is reached with no open blocker, and asks "continue or stop?" at `feature_token_budget`.

## Check Progress

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/pd-status   # items by status and phase, roadmaps, open blockers, retros owed
```

The SessionStart hook prints the active and blocked items, each roadmap's next ready item and the retros owed.

## Utilities

| Command | What it does |
|---------|-------------|
| `/pd:add-to-backlog <idea>` | Add a line to `backlog.md` without starting a feature |
| `/pd:retrospect` | Run a retro on a feature that owes one |
| `/pd:abandon-feature` | Set a feature to `abandoned` |
| `/pd:wrap-up` | End a session: commit WIP, write `## Now` and a handoff entry |

## File Layout

pd's artifacts live under `artifacts_root` (default `docs/dev_artifacts/`):

```
docs/dev_artifacts/
├── features/<id>/        # one folder per feature; <id> is YYYY-MM-DD-slug
│   ├── README.md         # frontmatter (status, phase, mode, branch, risk) and ## Now
│   ├── log.md            # append-only entries: phase, review, qa, run, decision, …
│   ├── shape.md          # ## Requirements + ## Design
│   ├── plan.md           # ## Plan: waves of task blocks
│   └── retro.md          # only when a retro trigger fired
├── plans/<id>.md         # a multi-feature plan with its roadmap
├── brainstorms/<id>.md   # a PRD, with its ## Log
├── rca/<id>.md           # a root-cause report, with its ## Log
└── backlog.md            # one line per idea
```

Everything else — progress, next ready items, open blockers — is computed by `pd-status` from these files.
