# Thin pd bake-off (T5.2)

The first live run of thin pd: one real feature, built through every stage on the installed plugin (v7.0.2), plus the probes for the checks that don't happen naturally. It settles plan §A7. Every result row below cites its evidence: a `log.md` entry, a commit, or a file path.

**If a check fails,** the rollout stops there. Revise the plan section it rests on, calvin it, and decide (§A7). T6.1 (adopting pedantic-drip) waits until every check passes and every question has an answer.

## Done already (2026-10-16)

- **The main checkout is on develop.** Through v7.0.1, `sync-cache.sh` copied the checked-out branch's plugin into the installed cache whenever a session started there; v7.0.2 removed it, so the installed copy is always the GitHub release. The unstaged `README.md` edits were saved to `agent_sandbox/2026-10-16/readme-unstaged-edits/README.md.patch` first.
- **Steps 1 and 2 below are done:** `~/projects/pd-bakeoff-backlog-sweep` exists. Its scaffold is commit `4574f97`; `pd-init` (7.0.1, run as a script) is commit `62185ec`, with the settings diff applied and `test_paths: [tests/]`, `fixture_paths: [fixtures/]` set by hand. `pd-lint` exits 0 and `pd-status` prints "no items".
- **A headless smoke session** (`claude -p`, plan mode, session `96f90855-7820-48d1-b7b9-724abba0c111`) in that repository:
  - received `pd_artifacts_root: docs/dev_artifacts` and `pd_base_branch: main` from the session-start hook;
  - listed 25 commands, 24 skills, the 4 workflows (`pd:implement-tasks`, `pd:verify-change`, `pd:research-fanout`, `pd:rca-fanout`) and 21 agents, every name with the `pd:` prefix.
- **v7.0.3 landed mid-run** (during the criteria sign-off): content past half a terminal opens in the browser, expectations render as cards, and `cleanup-stale-versions` spares a version a live session uses. A session started before it keeps running 7.0.2 until resumed.
- **v7.0.4 landed mid-run** (after the criteria sign-off): `pd-html` shows `<placeholders>` as text and warns, naming the line, on markdown that renders garbled, such as this run's `shape.md:54`. Resume the session (`claude -r`) to pick it up.
- **v7.0.5 landed mid-run** (after Contracts): each stage's checklist ends with its blocker bar; designing asks for nothing unrequested and evidence behind every risk; no backward compatibility without external consumers; Verify fixes a removal by deleting code. The Contracts below were approved under 7.0.4's checklist, so these rules didn't apply to them. Resume the session (`claude -r`) so Plan runs on 7.0.5.
- **What it found:** Claude Code ignores the repository's `permissions.allow` entries until the workspace is trusted. Check 8 depends on those rules, so accept the trust dialog the first time you open Claude Code there.

## Before you start

1. **Restart Claude Code**, so v7.0.2 loads. In a session, `/plugin` lists `pd` at 7.0.2.
2. **Leave the other pd repos alone.** fractorg, project_illium, illium-golive and cast-below still use the old layout. pd's hooks only suggest `/pd:adopt` there, and nothing adopts them before T6.

## Step 1: make the bake-off repository (done)

The feature is the backlog sweep tool (T5.1): a small Python CLI that sorts the legacy `docs/backlog.md` (a table of about 170 rows) into keep and archive. Archive means a row names the retired registry, MCP servers, UI or `.meta.json`. Its output feeds T6.1's MAP BY HAND step.

```bash
mkdir ~/projects/pd-bakeoff-backlog-sweep && cd ~/projects/pd-bakeoff-backlog-sweep
git init -b main
uv init --lib --name backlog_sweep && uv add --dev pytest
mkdir -p fixtures && cp ~/projects/pedantic-drip/docs/backlog.md fixtures/legacy-backlog.md
git add -A && git commit -m "scaffold: uv project and the legacy backlog fixture"
claude
```

## Step 2: set the project up (done, except trust)

`pd-init` wrote the config (`qa_battery: uv run pytest -q`) and applied the settings: `worktree.baseRef: "head"`, the spawn-depth cap and the allow rules for `git merge`, `git worktree` and `uv run pytest`. QA reads only exit codes; `pd-proof` reads the JUnit file each plan task's proving command writes.

When you open Claude Code there:
1. **Accept the trust dialog**, or the allow rules stay ignored.
2. **Note the task tools:** see whether the session offers `TaskCreate`/`TaskList` (check 5). The build session (Opus 5.5, 2026-10-16) listed them as deferred tools, without `CLAUDE_CODE_ENABLE_TODO_TOOLS`.

## Step 3: run the feature through every stage

```
/pd:secretary "a CLI that sorts fixtures/legacy-backlog.md into keep and archive: archive any row naming the retired entity registry, MCP servers, the UI server or .meta.json; print both lists and a count" --standard
```

Then follow each stage, answering its questions. Watch for these:

| Stage | Command | What to watch |
|-------|---------|---------------|
| Criteria | `/pd:specify` | calvin runs as `calvin-runner` and writes its ledger under `agent_sandbox/<date>/<feature id>/`. The ledger appearing proves little: the write guard lets every write through when `agent_type` is missing, so check 2's hook input needs the refusal probe in its row |
| Contracts | `/pd:design` | the review call: Codex first (your CLAUDE.md enables it), else the Claude fallback; one `review` entry in `log.md` |
| Plan | `/pd:create-plan` | at least one `[parallel-safe]` pair (the row parser and the rules), then the report and the CLI; each task has a proving command writing JUnit |
| Execute | `/pd:implement` | one worktree per task, each starting from the feature branch's HEAD; branches `pd/<id>/task-<n>`; the merger's proof lines in a `run` entry (checks 1 and 7) |
| Verify | `/pd:verify` | the code review beside `qa-executor`; whether `agentType: codex:codex-rescue` works inside the workflow (check 7) |
| Finish | `/pd:finish-feature` | a `metrics` entry with tokens and agent count; merged to `main` (check 6) |

**Drive part of it with `/goal`** (checks 4, 6, 8 and 9). After the plan is approved, the conductor writes a `goal:` line in `## Now` and prints a command like this:

```
/goal pd-status prints feature <id> as finish with no open blockers, or the user has said to stop
```

- **Check 9:** before typing it, ask Claude to start the goal itself, and record whether it can.
- **Check 8:** once it runs, leave it unattended. Record any permission prompt that stops it.

## Step 4: the probes

Run each probe as its own small feature in the same repository (`/pd:create-feature … --mode small`), so the main feature's record stays clean.

| Probe | How to provoke it | What should happen |
|-------|-------------------|--------------------|
| Hard stop (check 4) | During a `/goal` run, answer the conductor's AskUserQuestion with "stop" | The run ends; the Stop gate doesn't hold it |
| Flaky fixture (check 7) | A task whose test reads a counter file and fails on alternate runs | The merger re-runs the unexpected result; a third run decides a disagreement, and it is logged |
| Small budget (check 6) | Set `feature_token_budget` low (for example 50000) in `.claude/pd.local.md`, then `/goal` a probe feature | The gate asks "budget spent: continue or stop?" while `/goal` still judges the goal unmet |
| Resume (check 10) | Let one task merge, interrupt the run mid-task, remove the worktrees, then `/pd:implement` in a fresh session | The finished task merges once; only the remaining task runs |
| Escalation (check 10) | A task whose test fails the first two runs (a counter file again) | Its fix cycles reuse the branch; cycle 2 runs on the strongest model (the `run` entry and the agent transcript name it) |
| Retro trigger (T4.5) | Send a probe feature back twice (`phase <from> -> <to> (back)`), or record a `defect` entry after merge | Finish runs the retro and writes `retro.md` instead of a `note` |

## Where the evidence is

- **Feature state:** `"$(ls -d ~/.claude/plugins/cache/*/pd/*/scripts | head -1)/pd-status"`, and `pd-lint` from the same folder.
- **History:** `docs/dev_artifacts/features/<id>/log.md`: `run`, `review`, `qa`, `gate`, `phase` and `metrics` entries.
- **Branches and merges:** `git log --graph --oneline main` and `git branch -a | grep pd/`.
- **Token totals:** the gate's file `~/.claude/pd/gate/<repo key>/<feature id>.json`.
- **Models and hook input:** the agent transcripts under `~/.claude/projects/<project>/<session id>/subagents/` (check 2's model and effort, check 3's model, and the escalation probe's cycle 2).

## Results

Fill in each row during the run.

### Checks (§A7)

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | A task's worktree starts from the feature branch's HEAD, and the merger merges its commits | pending | |
| 2 | A plugin agent's `tools`, `model`, `effort` and `skills` apply through `agentType`; a subagent's hook input carries the parent `session_id` | pass, except `skills`: still to see | Criteria, session `fd57286f`: both `pd:calvin-runner` agents ran on `claude-opus-5-5` at effort `high` (frontmatter `opus`, `high`; the parent ran at `xhigh`) and used only `Skill`, `Read` and `Write` of their four tools. Hook input: a probe (scratch repo, `claude -p --session-id`, a gate file naming `agent_sandbox/ok.md`) had `pd:calvin-runner` write `ok.md`, allowed, then `bad.md`, refused with "calvin-runner may write only its ledger agent_sandbox/ok.md": only a hook input carrying `agent_type` and the parent's `session_id` reaches that message. Only the Claude fallback reviewers carry `skills:` (design-, plan- and code-quality-reviewer), so with Codex enabled it may stay unseen |
| 3 | A pinned reviewer model gets the 1M-token window as a subagent | pending | |
| 4 | A `/goal` run stops at a hard stop | pending | |
| 5 | The task list is available | pending | |
| 6 | Spend is recorded; the gate counts workflow agents, yields to background workflows, blocks on open blockers, and ends a goal at the cap | pending | |
| 7 | The merger's per-task check holds through `pd-proof`; `agentType: codex:codex-rescue` works inside a workflow | pending | |
| 8 | Auto mode lets workflow agents merge, remove worktrees and run tests unattended | pending | |
| 10 | Resume merges a finished task once and runs only the rest; escalation reuses the branch and runs cycle 2 on the strongest model | pending | |

### Questions (§A7)

| Item | Question | Answer |
|------|----------|--------|
| 6 | Could a `SessionEnd` hook write the session's total beside the gate's per-feature file? | pending |
| 6 | Does a "+Nk" turn target carry into turns the `/goal` hook starts? | pending |
| 9 | Can Claude start a `/goal` itself? | pending |

### Unverified until this run (build-tasks.md, Wave 4)

| Item | Result | Evidence |
|------|--------|----------|
| `${CLAUDE_SESSION_ID}` substitution in skills (the `goal:` line in `## Now`) | pending | |
| Plugin agent, skill and workflow names with the `pd:` prefix; plain skill names in `skills:` | partial: agents dispatch by prefixed name; workflows and `skills:` still to see | smoke session `96f90855` lists every name with the prefix; session `fd57286f` dispatched `agentType: pd:calvin-runner` twice |
| Subagent hook input carries `agent_type` and the parent `session_id` | pass | the write-guard refusal probe in check 2's row |
| The `background_tasks` status values the Stop gate reads | pending | |

### Probes

| Probe | Result | Evidence |
|-------|--------|----------|
| Hard stop | pending | |
| Flaky fixture | pending | |
| Small budget | pending | |
| Resume | pending | |
| Escalation | pending | |
| Retro trigger | pending | |

### The feature

| Item | Result | Evidence |
|------|--------|----------|
| Contracts: the review call | pass | `log.md` 14:37 `review design — codex (fallback: no)`: 5 blockers (R1 symlinked archive, R2 hard link, R3 empty re-run newline, R4 `\|\|ID\|…` header, R5 extra keys), 4 warnings, all fixed in `04011d1`; 14:42 scoped re-review approved, no blocker, `95d7bc5`. Session `fd57286f`: the full review's prompt carried designing's checklist inline and the pinned `{approved, issues, summary}` schema, `--model gpt-6-astra`; the re-review used the scoped schema. Design gate passes; `pd-lint` exits 0 (7.0.5 scripts, 2026-10-16 17:20). `pd-html` still warns once, on `shape.md:54` |
| The feature reaches `done` | pending | |
| `pd-lint` passes on it | pending | |
| Tokens and agent count recorded | pending | |

## When it passes

Record the result in `build-tasks.md`'s log, then start T6.1: run `/pd:adopt` in pedantic-drip. It begins with a dry run for you to review, and lists the unclassified items for MAP BY HAND, which the sweep tool's output helps sort.
