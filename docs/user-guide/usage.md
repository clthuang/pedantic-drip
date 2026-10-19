---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Usage

## Set a Project Up

```bash
/pd:init     # a new project: writes .claude/pd.local.md, proposes .claude/settings.json changes
/pd:adopt    # an old-layout pd project (docs/features/ without `sop: 1`): migrates it once
```

What `/pd:init` writes and proposes: [Set a Project Up](installation.md#set-a-project-up). Set `qa_battery` in `.claude/pd.local.md`: Verify needs it.

## Quick Start

`/pd:secretary` triages a request — work item (at a depth), brainstorm, RCA or specialist — states why, and routes:

```bash
/pd:secretary "add email validation to the signup form"
```

Or start directly:

```bash
/pd:brainstorm "your idea here"                          # Clarify: a PRD in brainstorms/<id>.md
/pd:root-cause-analysis "the export drops the last row"  # Clarify for a bug: rca/<id>.md
/pd:create-workitem "add user auth"                      # a standard work item and its branch
/pd:create-workitem "fix the pagination off-by-one" --mode express
```

A finished brainstorm or RCA becomes a work item through promotion:

```bash
/pd:create-workitem "<title>" --from brainstorms/<id>.md  # or --from rca/<id>.md
```

## The Standard Workflow

```bash
/pd:specify        # shape.md ## Requirements: B-numbered expectations, calvin, your sign-off
/pd:design         # shape.md ## Design: diagram, contracts, test strategy → review call
/pd:create-plan    # plan.md: task blocks with test cases → test-case review
/pd:implement      # implement-tasks: one implementer per task, the merger lands each
/pd:verify         # verify-change: code review beside QA, then fix cycles
/pd:finish-workitem # security review, docs, metrics, retro if owed, merge, cleanup
```

Each command invokes its stage skill. Before `phase:` moves on, `phase-gate.sh <phase> <workitem-dir>` must pass, and every `git commit` Claude runs is checked by `pd-lint --staged` (commits you type in a terminal aren't).

- **calvin:** a separately installed skill ([Optional](installation.md#optional)) that questions the criteria at `/pd:specify`; without it, `/pd:specify` asks whether to sign off anyway.
- **Small** (`--mode small`): design and plan are written in one sitting and reviewed in one joint call.
- **Express** (`--mode express`): `shape.md` holds a mini-spec with one task block; `/pd:implement` runs that one task and Verify is lighter.
- **Backward moves:** a wrong criterion or test case sends the work item back (`phase <from> -> <to> (back)` in `log.md`); merged tasks stay merged.

## Long Runs

Start a `/goal` run on a work item; the main session (the conductor) writes `goal: <id> target <phase> session <id>` to the README's `## Now`. The Stop hook holds the run until the target is reached with no open blocker, and asks "continue or stop?" at `workitem_token_budget`.

## Check Progress

Run `pd-status` as [Check It Works](installation.md#check-it-works) shows: it prints items by status and phase, roadmaps, open blockers and retros owed.

At the start of each session, the SessionStart hook gives Claude the active and blocked items, each roadmap's next ready item and the retros owed, so you can ask about them.

## Utilities

| Command | What it does |
|---------|-------------|
| `/pd:add-to-backlog <idea>` | Add a line to `backlog.md` without starting a work item |
| `/pd:retrospect` | Run a retro on a work item that owes one |
| `/pd:abandon-workitem` | Set a work item to `abandoned` |
| `/pd:wrap-up` | End a session: commit WIP, write `## Now` and a handoff entry |

Every command, with what it does: [README.md](../../README.md#commands).

## File Layout

pd's artifacts live under `{pd_artifacts_root}` (the `artifacts_root` key, default `docs/dev_artifacts/`):

```
{pd_artifacts_root}/
├── workitems/<id>/       # one folder per work item; <id> is YYYY-MM-DD-slug
│   ├── README.md         # frontmatter (status, phase, mode, branch, risk) and ## Now
│   ├── log.md            # append-only entries: phase, review, qa, run, decision, …
│   ├── shape.md          # ## Requirements + ## Design
│   ├── plan.md           # ## Plan: waves of task blocks
│   └── retro.md          # only when a retro trigger fired
├── plans/<id>.md         # a multi-item plan with its roadmap
├── brainstorms/<id>.md   # a PRD, with its ## Log
├── rca/<id>.md           # a root-cause report, with its ## Log
└── backlog.md            # one line per idea
```

Everything else — progress, next ready items, open blockers — is computed by `pd-status` from these files. Each file's sections: [workflow-artifacts.md](../technical/workflow-artifacts.md).
