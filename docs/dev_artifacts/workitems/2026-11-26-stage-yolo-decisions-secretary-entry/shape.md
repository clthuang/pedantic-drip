# Shape: Stage, YOLO decisions, secretary entry point, main-session read budget

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- **The main session stays lean:** past a budget the owner sets, the main session is refused raw reads and web lookups and is pointed to a research agent, so the strong model spends its tokens on decisions.
- **One entry point:** `/pd:secretary "<request>"` carries a work item from triage to finish as one goal run.
- **YOLO runs unattended:** after the owner confirms it once, the run decides every question itself, and each decision it makes for the owner carries a record: pros and cons, the trade-off, implications and a premortem.
- **A stage changes the trade-offs:** each work item is `mvp` or `production`. At mvp, reviews block only on a broken core flow, data loss or exposure, or security, and everything else becomes a harden-later warning. At production the bar stays as it is today.
- **Two existing sync problems are fixed:** the review schema restated in `references/workflow-results.md`, and the severity word `suggestion` used by three reviewer agents where the workflows say `note`.

### Non-goals

- **No new driver for YOLO:** `/goal`, `/loop` and new Workflow scripts are not used. The existing `Stop` gate drives goal runs.
- **No per-code-area stages and no third stage.**
- **No change to the safety rails:** fix-cycle caps, the token budget, the security review for `risk: security`, and blockers `R0` and `QB<n>`.
- **The read budget doesn't catch every way to read a file:** reads inside `$(...)`, `eval`, `bash -c`, scripts and interpreters go uncounted.
- **No choice of the main session's model:** that stays the owner's `/model` setting.
- **YOLO doesn't hold brainstorm or RCA items:** the `Stop` gate arms on work items only, so a YOLO run holds from promotion on.

### User stories

- As the owner, I type `/pd:secretary --yolo "<request>"`, confirm once, and come back to a finished work item whose `log.md` records every decision made for me.
- As the owner, I set `stage: mvp` once for a new project, so reviews stop blocking on edge cases and consistency. Later I promote a work item to production to harden it.
- As the owner, I set `main_read_budget`, so research reading happens in cheaper agents and only their pointers reach my main session.

### Expectations

Each one observable, with a unique id. Plan turns them into test cases.

**Stage: where it lives**

B1: `pd-new workitem "<title>"` with no `--stage`, in a repo whose `.claude/pd.local.md` has `stage: mvp` -> the new README frontmatter has `stage: mvp`
B2: `pd-new workitem "<title>"` with no `--stage` and no `stage:` key in the config -> the README frontmatter has `stage: production`
B3: `pd-new workitem "<title>" --stage mvp` with config `stage: production` -> the README frontmatter has `stage: mvp`
B4: `pd-new workitem "<title>" --stage beta` -> exit 2 with an argparse error naming the allowed values, and no work item directory is created
B5: `pd-new workitem "<title>"` with no `--stage` and config `stage: beta` -> a non-zero exit with a message naming the config key and the allowed values, and no work item directory is created
B6: `pd-lint` on a work item whose README has `stage: beta` -> `pd-lint: ERROR <README>:<line>: ...` naming `stage` and `beta`, exit 1
B7: a work item README with no `stage:` key (every work item created before this change) -> `pd-lint` reports no error for it, and `pd-status`, `phase-gate.sh` and `pd-review-prompt` all treat it as `production`
B8: `pd-status` -> every work item row shows its stage, and an open work item whose stage differs from the project default is marked as differing

**Stage: how it reaches reviewers**

B9: `pd-review-prompt verifying <work item dir>` on a work item with `stage: mvp` -> exit 0; stdout's first line is `Stage: mvp`, followed by the `## Review checklist` section of the verifying skill verbatim, the mvp paragraph of `references/stage-bars.md`, and the review-call schema of `references/workflow-results.md`
B10: the same on a work item with `stage: production` -> stdout's first line is `Stage: production`, and it carries the production paragraph and not the mvp one
B11: `pd-review-prompt designing planning <work item dir>` (a small work item's joint review) -> both skills' checklists, one stage paragraph and one schema
B12: `pd-review-prompt <skill> <dir>` where the skill has no `## Review checklist` section, or the directory has no README -> exit 1, a message on stderr, and nothing on stdout
B13: `verify-change` started with no `stage` in its args, or a `stage` other than `mvp` or `production` -> it throws an error naming `args.stage` before any agent runs
B14: a finished `verify-change` run -> its result carries `stage`, equal to the `stage` arg it was given
B15: `phase-gate.sh design|create-plan|verify <dir>` when the latest `review` entry in `log.md` says `Stage: mvp` and the README says `stage: production` (or the reverse) -> `GATE FAIL [<phase>]: ...` naming both stages, exit 1
B16: `phase-gate.sh` at the same exits when the latest `review` entry has no `Stage:` line -> the entry counts as `Stage: production`

**Stage: changing it on an open work item**

B17: moving a work item from `mvp` to `production` -> a `decision` entry, the README's `stage:` edited, and a backward move `phase <from> -> specify (back)` with `Invalidates:`, all committed before any other work
B18: moving a work item from `production` to `mvp` -> a `decision` entry and the README's `stage:` edited, with no backward move; the next gate requires a review that applied the new stage (B15)

**Risk detection on every depth**

B19: `phase-gate.sh verify <dir>` where `pd-lint --risk <base>..HEAD` reports a signal whose tag the README lacks, and no `decision` entry rules that tag out -> `GATE FAIL [verify]: ...` naming the signal and its tag, exit 1. This holds for express work items too, whose lighter Verify never runs `verify-change`
B20: the same diff after the README gains the tag, or after a `decision` entry rules the tag out -> that check passes

**Single entry point**

B21: `/pd:secretary "<feature request>"` without `--yolo` -> after the work item is created, one AskUserQuestion asks whether to run it to finish as a goal run. On yes, `## Now` holds `goal: <id> target finish session <session id>`, committed before Criteria starts
B22: the same, answered no -> no `goal:` line is written, and the work item proceeds as it does today
B23: triage in a project or work item at `stage: mvp`, for a request with no risk signal -> its `phase triage -> <first stage>` entry cites `stage: mvp`, and the only standard-depth triggers it applies are the `risk: security` and `risk: migration` tags

**YOLO**

B24: `/pd:secretary --yolo "<request>"` -> before any other step, one AskUserQuestion whose question starts with `Hard stop:` asks the owner to confirm YOLO. On yes, a `decision` entry quotes the answer, and `## Now` holds both the `goal: ... target finish session <session id>` line and `yolo: session <session id>`, committed
B25: the YOLO confirmation answered no -> no `yolo:` line, and the run continues as in B21
B26: AskUserQuestion called while this session's `yolo:` line is in an open work item's `## Now`, with any question that doesn't start with `Hard stop:` -> refused: hook exit 2, and stderr says to decide it and write a decision record carrying `Stage:`, `Pros/cons:`, `Trade-off:`, `Implications:` and `Premortem:`
B27: the same call where every question starts with `Hard stop:` -> allowed
B28: AskUserQuestion with no `yolo:` line, or with only another session's `yolo:` line -> allowed, unchanged from today
B29: a `decision` entry answered `A (conductor, on the user's behalf):` that lacks any of `Stage:`, `Pros/cons:`, `Trade-off:`, `Implications:` or `Premortem:` -> `pd-lint: ERROR ...` naming each missing line, exit 1. Print-mode decisions made for the user fall under the same rule
B30: `phase-gate.sh specify <dir>` with the sign-off answered `A (conductor, on the user's behalf):` -> passes only when `log.md` holds a YOLO confirmation `decision` entry quoting the owner's yes (B24); otherwise `GATE FAIL [specify]`, exit 1
B31: the `Stop` gate's token-cap and no-progress messages -> each tells the conductor to ask a question that starts with `Hard stop:`, so B26 lets it through
B32: the `Stop` gate finding the goal reached with no open blockers -> its message says to clear both the `goal:` and `yolo:` lines from `## Now` and commit

**Main-session read budget**

B33: no `main_read_budget` key in the config, or a repo with no pd config at all -> the hook allows every call and writes no state
B34: `main_read_budget: 3`, main session (the hook input has no `agent_type`): the 4th counted call in one turn -> refused, hook exit 2, and stderr names `pd:codebase-explorer`
B35: `main_read_budget` set, main session: WebFetch or WebSearch -> refused on the first call, and stderr names `pd:internet-researcher`
B36: the same calls from a subagent (the hook input has `agent_type`) -> allowed, and not counted
B37: main session, Read of a file under `artifacts_root` or under the plugin root -> allowed, and not counted
B38: counted calls are Read, Grep, `mcp__codegraph__codegraph_explore`, and any Bash command line in which a simple command's first word is `cat`, `head`, `tail`, `less`, `more`, `sed`, `awk`, `grep`, `egrep`, `fgrep`, `rg`, `find` or `fd`. Glob, `ls` and every other Bash command are not counted
B39: a turn starts at each user prompt and each time the `Stop` gate holds a stop -> the count goes back to zero at both
B40: the read-budget hook or the YOLO hook failing to run (a crash, unreadable state) -> the call is allowed, with one line on stderr naming the hook

**Existing sync problems**

B41: a field of the review-call schema changed in only one of `workflows/verify-change.js` and `references/workflow-results.md` -> the plugin's test suite fails, naming both files
B42: `grep -nw suggestion` over the severity enums and severity tables of `security-reviewer.md`, `ds-analysis-reviewer.md` and `ds-code-reviewer.md`, and the severity line of `retro-facilitator.md` -> no hits; their lowest severity reads `note`. The fix-text field named `suggestion` in their output schemas is a field name, not a severity, and stays

**Measures (owner-run probes at Verify)**

B43: Probe: one fixed small request run once with `stage: mvp` and once with `stage: production` -> the mvp run's `log.md` records fewer blocker findings and no more fix cycles than the production run, and its harden-later warnings appear as backlog lines
B44: Probe: `claude-mem:agent-cost-report` over one session without `main_read_budget` and one comparable session with it -> the report shows the main session's input tokens from read-tool results for both, so the owner can compare them

### Scope

- **In:**
  - **Stage:** `STAGES` vocabulary; the `stage:` config key and frontmatter field; `pd-new --stage`; `pd-lint`, `pd-status` and `phase-gate.sh` changes; the new `pd-review-prompt` script; `references/stage-bars.md`; `verify-change`'s `stage` arg; the `Stage:` line on review entries; the mvp forms of `specifying`'s edge-case rule and `planning`'s `proof: green-only` rule; finish turning harden-later warnings into backlog lines; `/pd:init` asking for the stage once.
  - **Risk detection:** `phase-gate.sh verify` runs `pd-lint --risk`.
  - **Entry point and YOLO:** `/pd:secretary`'s goal-run offer and `--yolo`; the `yolo:` line; the AskUserQuestion hook; the decision-record lines and their `pd-lint` check; the `Hard stop:` prefix in the `Stop` gate's messages and in `workflow-transitions`; the YOLO sign-off rule in `specifying` and `phase-gate.sh specify`.
  - **Read budget:** the main-session read-budget hook and its reset at the `Stop` gate; the `main_read_budget` config key; loosening `workflow-transitions`' Dispatch line so `codebase-explorer`, `internet-researcher`, `investigation-agent` and `skill-searcher` may be dispatched at any stage.
  - **Sync fixes:** the review-schema drift test; `note` in the three reviewer agents and in `retro-facilitator`.
  - **Docs sync:** `README.md`, `README_FOR_DEV.md`, `plugins/pd/README.md` (hooks, scripts and counts), `docs/dev-guide/hook-development.md`.
- **Out:**
  - **The user-level codegraph `UserPromptSubmit` hook:** it isn't pd's.
  - **Migrating existing work items:** an item without `stage:` reads as production (B7), so open items in other adopted projects need no edit.
  - **Old YOLO features:** pausing and resuming after usage limits (`yolo_usage_wait`, `yolo_usage_cooldown`).
  - **Changing how `implement-tasks` executes tasks:** worktrees, the merger and the proof stay as they are.

### Edge cases and must-nots

**Edge cases**
- **An item created before this change:** it has no `stage:` and its review entries have no `Stage:`; both read as production (B7, B16).
- **The project default flips while items are open:** the open items keep their own `stage:`, and `pd-status` marks the ones that differ (B8).
- **Two sessions on one work item:** `goal:` and `yolo:` lines carry a session id, so one session's YOLO never silences another session's questions (B28).
- **A `yolo:` line left behind by a crashed session:** a new session has a different id, so the old line has no effect. Clearing it is the same as clearing a stale `goal:` line.
- **A repo without pd config:** every new hook leaves on its fast path (B33).
- **A Bash command line that reads through a pipe:** `git log | grep x` is counted, since `grep` starts a simple command. `bash -c "cat f"` is not counted (Non-goals).
- **A goal run with no user prompts:** the `Stop` gate's hold starts a new turn (B39), so a long run is never locked out of reading.

**Hard stops that stay in YOLO** (each asked with the `Hard stop:` prefix):
- **The token cap:** a run that overspends never asks otherwise. The bake-off logged a 61× overrun.
- **No progress:** a stuck run would loop forever.
- **A merge conflict:** a wrong resolution can silently lose work.
- **A destructive operation:** force-pushing, deleting a branch, worktree or data this run didn't create, or writing a secret. Each of these is hard to undo.

**Must-nots**
- **Never answer the YOLO confirmation on the owner's behalf:** it is the one consent that turns autonomy on.
- **Never relax at mvp:** the security review for `risk: security`, blockers `R0` and `QB<n>`, the token budget, or validation at trust boundaries. These protect the user from harm, whatever the stage.
- **Never refuse a subagent's read, or the main session's read of a file it writes under `artifacts_root`:** research would stop, or the conductor couldn't update its own artifacts.
- **Never block every read when a hook breaks:** a crash locking the main session out would stall all work (B40).
- **Never store the stage anywhere but the config default and the work item's frontmatter:** a third copy would drift. Review entries and decision records only record the stage they applied.
- **Never change behaviour in a repo that sets none of the new keys:** no `stage:` means today's bar, no `main_read_budget` means no read hook, and no `yolo:` line means questions as today.

## Design

<!-- Contracts stage. Design input: agent_sandbox/2026-11-26/pd-stage-yolo-proposal/proposal.md -->
