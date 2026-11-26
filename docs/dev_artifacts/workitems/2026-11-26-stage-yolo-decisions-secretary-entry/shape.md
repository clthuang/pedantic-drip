# Shape: Stage, YOLO decisions, secretary entry point, main-session read budget

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- **The main session stays lean:** once the owner sets a read budget, raw reads past it are refused, web lookups are refused outright, and each refusal points to a research agent.
  - **Why this saves tokens:** a read result stays in the main session's context and is re-sent on every later turn. A research agent's reading stays in that agent's context, and only its answer comes back.
  - **How it's judged:** the owner reads a before-and-after cost report and rules (B44; log decision-4, calvin cycle 1).
- **One entry point:** `/pd:secretary "<request>"` triages, creates the item and, on the owner's yes, carries it to finish as one goal run.
- **YOLO runs unattended:** after the owner confirms it once, the whole session decides on the owner's behalf.
  - **What counts as a decision made for the owner:** every question the conductor would otherwise put to the owner through AskUserQuestion. Each is written as a `decision` entry answered `A (conductor, on the user's behalf):`, with a record: pros and cons, the trade-off, implications and a premortem.
  - **What doesn't count:** the conductor's routine rulings (`A (conductor):`, such as wording) are not decisions made for the owner.
  - **Where the run ends:** it opens a pull request, settles CI and the automated review, and stops before the merge.
- **A stage changes the trade-offs:** each work item is `mvp` or `production`.
  - **At mvp:** a review finding is a blocker only when, left unfixed, an expectation in `shape.md` fails on the input it names, data is lost or exposed, or a security hole opens. Everything else becomes a harden-later warning: an issue with severity `warning` and category `harden-later`. The rules listed under "Never relax at mvp" stay in force at mvp too.
  - **At production:** the bar stays as it is today. Today's bar is what the owner called "too production-considering" (log 13:24 note).
- **Two existing sync problems are fixed:**
  - **The review-call schema exists twice,** in `references/workflow-results.md` and in `workflows/verify-change.js`, with nothing tying them together. Two copies are unavoidable: the workflow script can read no file (its only inputs are `args`, verified 2026-11-26), and the conductor's review call needs the schema inline from markdown. So a test ties the two copies together.
  - **A severity word differs:** three reviewer agents define their lowest severity as `suggestion`, and `retro-facilitator` reads that word, where the workflows say `note`.

### Non-goals

- **No new driver for YOLO:** the existing `Stop` gate drives goal runs.
  - **Not `/goal`:** Claude can't start it (`docs/dev_artifacts/plans/2026-10-14-thin-pd/bake-off.md:120`), and the gate drives goal runs alone (F12, `bake-off.md:177`).
  - **Not `/loop`:** it re-runs a prompt on a timer.
  - **Not a new Workflow script:** workflows were the owner's token-cost complaint (log 13:24 note).
- **No per-code-area stages and no third stage.**
- **No change to the safety rails:** fix-cycle caps, the token budget (`workitem_token_budget`, enforced by the `Stop` gate), the security review for `risk: security`, and blockers `R0` and `QB<n>`. `main_read_budget` is unrelated to the token budget: it is a per-turn count of read calls.
- **The read budget doesn't catch every way to read a file:** reads inside `$(...)`, `eval`, `bash -c`, scripts and interpreters go uncounted.
- **No enforcement that research agents return only pointers:** the `researching` skill asks for it, and this change assumes it.
- **No choice of the main session's model:** that stays the owner's `/model` setting.
- **YOLO never merges:** the merge into the base branch stays the owner's (log decision-2, calvin cycle 1).

### User stories

- As the owner, I type `/pd:secretary --yolo "<request>"`, confirm once, and come back to an open pull request, with CI and the automated review settled and every decision made for me recorded in `log.md`.
- As the owner, I set `stage: mvp` once for a new project, so reviews stop blocking on edge cases and consistency. Later I open a production work item to harden what an mvp item shipped.
- As the owner, I set `main_read_budget`, so research reading happens in cheaper agents and only their answers reach my main session.

### Expectations

Each one observable, with a unique id. Plan turns them into test cases.

**Stage: where it lives**

B1: `pd-new workitem "<title>"` with no `--stage`, in a repo whose `.claude/pd.local.md` has `stage: mvp` -> the new README frontmatter has `stage: mvp`
B2: `pd-new workitem "<title>"` with no `--stage` and no `stage:` key in the config, or no config at all -> the README frontmatter has `stage: production`
B3: `pd-new workitem "<title>" --stage mvp` with config `stage: production` -> the README frontmatter has `stage: mvp`
B4: `pd-new workitem "<title>" --stage beta` -> exit 2 with an argparse error naming the allowed values, and no work item directory is created
B5: `pd-new workitem "<title>"` with no `--stage` and config `stage: beta` -> exit 1 with `pd-new: refused: ...` naming the config key and the allowed values, and no work item directory is created
B6: `pd-lint` on a work item whose README has `stage: beta` -> `pd-lint: ERROR <README>:<line>: ...` naming `stage` and `beta`, exit 1
B7: a work item README with no `stage:` key (every work item created before this change) -> `pd-lint` reports no error for it, and `pd-status`, `phase-gate.sh` and `pd-review-prompt` all treat it as `production`
B8: `pd-status` -> every work item row shows its stage. An open work item whose stage differs from the project default (the config's `stage:`, else `production`) shows its stage with a `*`, under a footer line `* stage differs from the project default (<default>)`

**Stage: how it reaches reviewers**

B9: `pd-review-prompt verifying <work item dir>` on a work item with `stage: mvp` -> exit 0. Stdout's first line is `Stage: mvp`, followed by the verifying skill's `## Review checklist` section verbatim, the mvp paragraph of `references/stage-bars.md`, and the review-call schema of `references/workflow-results.md`
B10: the same on a work item with `stage: production` -> stdout's first line is `Stage: production`, and it carries the production paragraph and not the mvp one
B11: `pd-review-prompt designing planning <work item dir>` (a small work item's joint review) -> both skills' checklists, one stage paragraph and one schema
B12: `pd-review-prompt <skill> <dir>` where the skill has no `## Review checklist` section, or the directory has no README -> exit 1, a message on stderr, and nothing on stdout
B13: `verify-change` started with no `stage` in its args, a `stage` other than `mvp` or `production`, or an `args.checklist` whose first line isn't `Stage: <args.stage>` -> it throws an error naming the arg before any agent runs
B14: a finished `verify-change` run -> its result carries `stage`, equal to the `stage` arg it was given
B15: `phase-gate.sh design|create-plan|verify <dir>` when the latest `review` entry (the last one in `log.md`) says `Stage: mvp` and the README says `stage: production`, or the reverse -> `GATE FAIL [<phase>]: ...` naming both stages, exit 1. With no `review` entry in `log.md`, the check doesn't apply, since today's gates don't require one before Verify
B16: `phase-gate.sh` at the same exits when the latest `review` entry has no `Stage:` line -> the entry counts as `Stage: production`
B45: a review call (by the conductor, or inside `verify-change`) -> the reviewer's JSON carries a `stage` field echoing its prompt's `Stage:` line, and the `review` entry's `Stage:` line copies that field

**Stage: changing it on an open work item**

B17: the owner asks to move an open work item from `mvp` to `production` -> a `decision` entry, the README's `stage:` edited, and a backward move `phase <from> -> specify (back)` with `Invalidates:`, all committed before any other work
B18: the owner asks to move an open work item from `production` to `mvp` -> a `decision` entry and the README's `stage:` edited, with no backward move. The next gate requires a review that applied the new stage (B15)
B46: the owner asks to change the stage of a work item with `status: done` -> refused, with a reply proposing a new production work item seeded from the backlog lines that item's harden-later warnings produced (log calvin cycle 1, row 17 ruling)

**Stage: what mvp relaxes**

B47: Criteria on a work item at `stage: mvp` -> `shape.md`'s edge cases name only those that lose or expose data, make an expectation fail, or cross a trust boundary, and list the rest under a `Deferred:` line
B48: `pd-lint` on a plan task with `proof: green-only (mvp)` -> no error on a work item at `stage: mvp`, and `proof: green-only needs a reason` (today's error) on one at `stage: production`
B49: `phase-gate.sh finish <dir>` on an mvp work item whose `review` entries hold `harden-later` issues -> `GATE FAIL [finish]: ...` until `backlog.md` has a line ending `(from: workitems/<id>)` that names each of those issue ids
B50: `pd-init` on a repo with no `.claude/pd.local.md` -> the written config has `stage: production`. `/pd:init` asks mvp or production through AskUserQuestion and writes the answer

**Risk detection on every depth**

Why: the owner ruled that at mvp only the risk tags force standard depth (log 13:24 decision-2). Today only `verify-change` runs `pd-lint --risk`, and express items skip it (`plugins/pd/skills/verifying/SKILL.md:42`), so without this section that ruling would have no detector on the express path.

B19: `phase-gate.sh verify <dir>` where `pd-lint --risk <base>..HEAD` reports a signal whose tag the README lacks, and no `decision` entry carries `Risk: none (<tag>) — <reason>` for it -> `GATE FAIL [verify]: ...` naming the signal and its tag, exit 1. This holds at every depth and in every repo (log calvin cycle 1, row 29 ruling)
B20: the same diff after the README gains the tag, or after such a `decision` entry -> that check passes

**Single entry point**

B21: `/pd:secretary "<feature request>"` without `--yolo` -> after the work item is created, one AskUserQuestion asks whether to run it to finish as a goal run. On yes, `## Now` holds `goal: <id> target finish session <session id>`, committed before Criteria starts
B22: the same, answered no -> no `goal:` line is written, and the work item proceeds as it does today
B23: triage at stage mvp (the config's `stage: mvp`, or `--stage mvp` passed to `/pd:secretary`) for a request with no security or migration signal -> its `phase triage -> <first stage>` entry cites `stage: mvp`, and it applies no standard-depth trigger. The two risk tags, `security` and `migration` (`RISKS` in `pd_common.py:21`), are the only triggers left at mvp

**YOLO: turning it on**

B24: `/pd:secretary --yolo "<request>"` -> before any other step, one AskUserQuestion whose question starts with `Hard stop:` asks the owner to confirm YOLO. On yes, YOLO is on for this session from that moment, before any item exists. The first item the run creates gets a `decision` entry quoting the answer, with a `Session: <session id>` line, and the item's `## Now` holds its `goal:` line, committed
B25: the YOLO confirmation answered no -> YOLO stays off, and the run continues as in B21
B51: a new session working on an item a YOLO session left unfinished -> YOLO is off for it. `/pd:secretary --yolo` on that item asks the confirmation again (B24) and writes a new `goal:` line for the new session

**YOLO: what it decides and what it can't**

B26: AskUserQuestion while YOLO is on for this session, with any question that doesn't start with `Hard stop:` -> refused, hook exit 2. Stderr says to decide it and write a decision record carrying `Session:`, `Stage:`, `Pros/cons:`, `Trade-off:`, `Implications:` and `Premortem:`
B27: the same call where every question starts with `Hard stop:` -> allowed
B28: AskUserQuestion in a session where YOLO is off -> allowed, unchanged from today, even when another session on the same item has YOLO on
B29: a `decision` entry answered `A (conductor, on the user's behalf):` that lacks any of `Session:`, `Stage:`, `Pros/cons:`, `Trade-off:`, `Implications:` or `Premortem:` -> `pd-lint: ERROR ...` naming each missing line, exit 1. This holds whatever wrote the entry (a YOLO run or a `claude -p` run), in every repo (log calvin cycle 1, row 29 ruling)
B30: `phase-gate.sh specify <dir>` with the sign-off answered `A (conductor, on the user's behalf):` -> passes only when an earlier YOLO confirmation `decision` entry in `log.md` has the same `Session:` line as the sign-off. Otherwise `GATE FAIL [specify]`, exit 1
B52: while YOLO is on for this session, a Bash command line with `git push` and `--force`, `-f` or `--force-with-lease`; `git branch` with `-D`, `-d` or `--delete`; `git worktree remove`; `git push --delete` or `git push <remote> :<branch>`; or `rm` with `-r`, `-R` or `-rf` on a path outside `agent_sandbox/` -> refused, hook exit 2, and stderr says to ask a `Hard stop:` question first
B53: the same command line after a `Hard stop:` question naming it is answered yes -> it runs once. The next identical command is refused again
B54: while YOLO is on for this session, `git commit`, `git merge --continue`, `git rebase --continue` or `git cherry-pick --continue` while the repo is mid-merge, mid-rebase or mid-cherry-pick with conflicts -> refused until a `Hard stop:` question about the conflict is answered
B55: a YOLO run reaching the end of finish -> it pushes the branch and opens a pull request, waits for CI and the automated review, fixes what they raise (each fix with its decision record), then asks `Hard stop: ready to merge?`. It never merges (log calvin cycle 1, row 33 rulings)

**YOLO: the Stop gate**

B31: the `Stop` gate's token-cap and no-progress messages -> each tells the conductor to ask a question that starts with `Hard stop:`, so B26 lets it through
B32: the `Stop` gate finding the goal reached with no open blockers -> its message says to clear the `goal:` line from `## Now` and commit. YOLO stays on for the session until it ends or the owner turns YOLO off
B56: a brainstorm or RCA item with this session's `goal:` line, and no work item yet promoted from it -> the `Stop` gate holds the stop (exit 2). Once a work item is promoted from it, the gate holds that work item's goal instead (log calvin cycle 1, rows 6, 15 and 28 ruling)

**Main-session read budget**

B33: no `main_read_budget` key in the config, or a repo with no pd config at all -> the hook allows every call and writes no state
B34: `main_read_budget: 3`, main session (the hook input has no `agent_id`; `agent_type` can't be used, since a session started with `--agent` carries it too): the 4th counted call in one turn -> refused, hook exit 2, and stderr names `pd:codebase-explorer`
B35: `main_read_budget` set, main session: WebFetch or WebSearch -> refused on the first call, and stderr names `pd:internet-researcher`
B36: the same calls from a subagent (the hook input has `agent_id`) -> allowed, and not counted. An Agent tool result reaching the main session is not a read call and is not counted
B37: main session, Read of any file under `artifacts_root` or under the plugin root -> allowed, and not counted
B38: main session with the budget set, a call to Read, Grep or `mcp__codegraph__codegraph_explore`, or a Bash command line in which a simple command's first word is `cat`, `head`, `tail`, `less`, `more`, `sed`, `awk`, `grep`, `egrep`, `fgrep`, `rg`, `find` or `fd` (commands whose output is file content or search hits) -> counts toward the budget, while Glob, `ls` and every other Bash command do not
B39: a turn starts at each `UserPromptSubmit` event (a typed prompt, or a background agent reporting back) and each time the `Stop` gate holds a stop -> the count goes back to zero at both
B40: the read-budget hook or a YOLO hook failing to run (a crash, unreadable state) -> the call is allowed, with one line on stderr naming the hook
B57: while this session's `run in flight:` line is in a work item's `## Now` -> the read budget refuses nothing. The docs don't say whether agents launched by a workflow carry `agent_id`, so a workflow run must never be starved

**Existing sync problems**

B41: a field of the review-call schema, the new `stage` field included, changed in only one of `workflows/verify-change.js` and `references/workflow-results.md` -> `node plugins/pd/workflows/tests/test-workflows.mjs` (a `qa_battery` command) fails, naming both files
B42: `grep -nw suggestion` over the severity enums and severity tables of `security-reviewer.md`, `ds-analysis-reviewer.md` and `ds-code-reviewer.md`, and the severity line of `retro-facilitator.md` -> no hits; their lowest severity reads `note`. The fix-text field named `suggestion` in their output schemas is a field name, not a severity, and stays

**Measures (owner-run probes at Verify, judged by the owner)**

B43: Probe: one fixed small request run once at `stage: mvp` and once at `stage: production` -> a `note` entry records each run's blocker findings, fix cycles, harden-later backlog lines and token total (from the `Stop` gate's files), and the owner's ruling on them follows as a `decision` entry
B44: Probe: `claude-mem:agent-cost-report` over one session without `main_read_budget` and one comparable session with it -> a `note` entry records each session's main-session tokens from read-tool results, and the owner's ruling follows as a `decision` entry

### Scope

- **In:**
  - **Stage:** the `STAGES` vocabulary; the `stage:` config key and frontmatter field; `pd-new --stage`; changes to `pd-lint`, `pd-status`, `phase-gate.sh` and `pd-init`; the new `pd-review-prompt` script; `references/stage-bars.md`; `verify-change`'s `stage` arg; the `stage` field in the review-call schema and the `Stage:` line on review entries; the mvp forms of `specifying`'s edge-case rule and `planning`'s `proof: green-only` rule; finish turning harden-later warnings into backlog lines.
  - **Risk detection:** `phase-gate.sh verify` runs `pd-lint --risk`.
  - **Entry point:** `/pd:secretary`'s goal-run offer and the `--stage` option.
  - **YOLO:** `--yolo`; the session's YOLO state; the AskUserQuestion hook; the destructive-command and merge-conflict hook; the decision-record lines and their `pd-lint` check; the `Hard stop:` prefix in the `Stop` gate's messages and in `workflow-transitions`; the YOLO sign-off rule in `specifying` and `phase-gate.sh specify`; the gate holding brainstorm and RCA goals; finish's pull-request step under YOLO.
  - **Read budget:** the main-session read-budget hook and its reset at the `Stop` gate; the `main_read_budget` config key; loosening `workflow-transitions`' Dispatch line so `codebase-explorer`, `internet-researcher`, `investigation-agent` and `skill-searcher` may be dispatched at any stage. That last change is verifiable only by reading the diff, so its check is specified at Contracts.
  - **Sync fixes:** the review-schema drift test; `note` in the three reviewer agents and in `retro-facilitator`.
  - **Docs sync:** `README.md`, `README_FOR_DEV.md`, `plugins/pd/README.md` (hooks, scripts and counts), `docs/dev-guide/hook-development.md`.
- **Out:**
  - **The user-level codegraph `UserPromptSubmit` hook:** it isn't pd's.
  - **Migrating existing work items:** an item without `stage:` reads as production (B7), so open items in other adopted projects need no edit. A census of the 20 pd repos on 2026-11-26 found no entry or open express item that B19 or B29 would affect.
  - **Old YOLO features not brought back:**
    - pausing and resuming after usage limits (`yolo_usage_wait`, `yolo_usage_cooldown`);
    - propagating a `[YOLO_MODE]` flag into dispatched prompts, since agents never ask the owner;
    - the SessionStart secretary-context injection;
    - the `/secretary orchestrate` subcommand, which `--yolo` replaces.
  - **Old YOLO features kept, reshaped:** the hard stops (now enforced by hooks), and deciding for the owner (now with records instead of "pick the recommended option").
  - **Watching the pull request past CI and the automated review:** later human comments are the owner's, or `/steward`'s.
  - **Changing how `implement-tasks` executes tasks:** worktrees, the merger and the proof stay as they are.

### Edge cases and must-nots

**Edge cases**
- **An item created before this change:** it has no `stage:`, and its review entries have no `Stage:`. Both read as production (B7, B16).
- **The project default flips while items are open:** the open items keep their own `stage:`, and `pd-status` marks the ones that differ (B8).
- **Two sessions on one work item:** YOLO and `goal:` lines are per session, so one session's YOLO never silences another session's questions (B28).
- **A session ends mid-run:** YOLO ends with it; the next session confirms again (B51). A stale `goal:` line has no effect on a new session, as today.
- **A YOLO conductor asks in plain text and ends its turn:** the goal run's `Stop` gate holds the stop, so nothing waits for an answer that YOLO should have decided.
- **A repo without pd config:** every new hook leaves on its fast path (B33).
- **A Bash command line that reads through a pipe:** `git log | grep x` is counted, since `grep` starts a simple command. `bash -c "cat f"` is not counted (Non-goals).
- **Several hooks on one call:** matching hooks run in parallel, so each one sees the command line as the model wrote it (code.claude.com/docs/en/hooks).
- **A goal run with no typed prompts:** the `Stop` gate's hold starts a new turn (B39), so a long run is never locked out of reading.
- **A workflow running:** the read budget stands down (B57).

**Hard stops that stay in YOLO** (each asked with the `Hard stop:` prefix):
- **The token cap:** a run that overspends never asks otherwise. The thin-pd bake-off logged a 61× overrun (`docs/dev_artifacts/plans/2026-10-14-thin-pd/bake-off.md:182`, F21).
- **No progress:** a stuck run would loop forever.
- **A merge conflict** (B54): a wrong resolution can silently lose work.
- **A destructive operation** (B52): force-pushing, or deleting a branch, worktree or files outside `agent_sandbox/`. Each is hard to undo.
- **The merge itself** (B55): it is outward-facing, and the owner keeps it.

**Must-nots**
- **Never answer the YOLO confirmation on the owner's behalf:** it is the one consent that turns autonomy on.
- **Never relax at mvp:** the security review for `risk: security`, blockers `R0` and `QB<n>`, the token budget, or validation at trust boundaries. These protect the user from harm, whatever the stage.
- **Never refuse a subagent's read, or the main session's read under `artifacts_root`:** research would stop, or the conductor couldn't work on its own artifacts.
- **Never block every read when a hook breaks:** a crash locking the main session out would stall all work (B40).
- **Never store the stage as a setting anywhere but the config default and the work item's frontmatter:** a third copy would drift. Review entries, decision records and workflow results only record the stage they applied.
- **Never change behaviour in a repo that sets none of the new keys,** except the risk check (B19) and the decision-record lint (B29). The owner ruled those apply everywhere, and the census found nothing they affect. Otherwise: no `stage:` means today's bar, no `main_read_budget` means no read hook, and no YOLO confirmation means questions as today.

## Design

<!-- Contracts stage. Design input: agent_sandbox/2026-11-26/pd-stage-yolo-proposal/proposal.md -->
