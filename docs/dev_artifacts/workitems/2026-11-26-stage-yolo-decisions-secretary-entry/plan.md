---
from_shape: 9b6d8d38119113b3d5aff149d4fe447232e7e64d
---
# Plan: Stage, YOLO decisions, secretary entry point, main-session read budget

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

Twelve tasks in three waves.

- **Wave 1, the foundations:** the shared helpers, the shell parser with the hook fixtures, the two new CLIs, and the severity rename. They depend on nothing new.
- **Wave 2, the consumers:** the three hooks, the stage scripts, the lint and gate checks, and the review prompt with the schema.
- **Wave 3, what binds them:** the conductor prose, then registration and docs.

Every task's files are disjoint from the others in its wave, so all twelve are `[parallel-safe]`.

**Terms the cases share**

- **`pd_repo`:** the existing fixture in `plugins/pd/scripts/conftest.py`, an adopted scratch repository with a work item committed. "Config `stage: mvp`" means a line added to its `.claude/pd.local.md`.
- **`gate_home` and `run_hook`:** the fixtures Task 2 adds in `plugins/pd/hooks/conftest.py` (shape.md Test strategy).
  - **`gate_home`:** a temporary HOME holding `.claude/pd/gate/`.
  - **`run_hook(script, payload)`:** pipes the HookInput JSON into the hook with `HOME` and `CLAUDE_PLUGIN_ROOT` set, and returns the exit code and stderr.
  - **Session ids:** payloads use `session_id` `s1`. "YOLO on" means `gate_home` holds `s1.yolo`.
  - **Scratch repos:** made by `git init` under `tmp_path`, with the payload's `cwd` inside them.
- **Allowed:** in a hook case, exit 0 and empty stderr. B40's fail-open path prints a line on stderr, so it can't pass for an allowed case. Read-budget cases also state the size of `s1.reads`.
- **Refused:** exit 2, with stderr holding the contract's refusal text for that rule (YoloGuard, ReadBudget), never the "check failed" text.
- **The fake `gh`:** a `gh` script first on `PATH`, replaying the outputs probed in shape.md "Probes of parsed output", and counting its calls in a file.
  - **`--json` replies:** exit 0 with the list on stdout, whatever the buckets (cli/cli PR 14927's failure exited 0).
  - **Pending:** exits 8 with the list on stdout, as plain `gh` does for pending checks.
  - **No checks:** exits 1, with `no checks reported on the 'x' branch` on stderr.
  - **No such PR:** exits 1 with `no pull requests found` on stderr.
- **Self-test and suite cases:** each existing suite that writes no JUnit is run once, inside the task's pytest file, asserting exit 0. That covers the scripts' `--self-test`, the bash suites, `test-workflows.mjs`, `validate.sh` and `check-doc-drift.sh`. A task runs every such suite that reads a file it edits.
- **Absence cases:** each names its search and that search's scope.
- **Unchanged behaviour:** a case for behaviour that holds today also asserts a fact true only after the change (B7, B16, B22, B25, B28, B33).
- **Shared config:** two new keys, and no existing value changes.
  - **`stage` consumers:** `CONFIG_DEFAULTS` (Task 1), `pd-new`, `pd-status` and `pd-init` (Task 8), `pd-review-prompt` through `item_stage` (Task 10), `init.md` (Task 11), and `getting-started.md`'s config table (Task 12).
  - **`main_read_budget` consumers:** the read-budget hook (Task 6) and `getting-started.md` (Task 12).
  - **`pd-adopt`:** its retired-field pattern (`pd-adopt:43`) matches neither key, so `pd-adopt` keeps both.

**Expectations proven outside pytest, at Verify** (shape.md "Live probes at Verify", headless where possible: `decision@2026-11-26 15:55+08:00`)

- **Headless runs:** `claude -p --plugin-dir plugins/pd --session-id <uuid> --output-format stream-json --verbose`, in a scratch repo under `agent_sandbox/<date>/<id>/probe-repo`. Evidence for each is the stream-json path and the lines showing its outcome, in a `qa` entry.
  - **B17, B18 and B46:** prepared items, each with a stage-change request. Evidence: the `decision` entry, the README's `stage:`, the `(back)` move and the commit order, or the refusal text.
  - **B23 and B59:** `/pd:secretary --stage mvp "<a request with no security or migration signal>"`. Evidence: the triage entry cites `stage: mvp`, `mode:` isn't forced to standard, and the README has `stage: mvp`.
  - **B26's model half:** with `s1.yolo` made for the run's `--session-id`, a prompt asks for a question to the user. Evidence: the hook's refusal in the stream, then a decision entry carrying the six record lines.
  - **Whether a workflow's agents carry `agent_id`:** a one-agent Workflow run under a logging PreToolUse hook passed with `--settings`. Evidence: the logged hook inputs.
- **Notes for the owner to try later:** each goes into a `note` entry with its steps, since `claude -p` answers no AskUserQuestion and takes no `!` command.
  - A1: `! git branch -d <a throwaway branch>` with YOLO on.
  - B21, B22, B24 and B25.
  - B51's re-confirmation.
  - Whether a refused question stays hidden from the owner.
- **B55:** this work item's own pull request, at its finish, in the owner's session.
- **B43 and B44:** the owner runs them, and each ruling is a `decision` entry (B61).
- **Their cases below:** Task 11 checks that each instruction exists, and Task 9 checks that the finish gate requires the rulings.

### Wave 1

#### Task 1: the shared helpers in pd_common, with pd-lint --risk reading them [parallel-safe]
- contract: shape.md ## Design, CommonHelpers; LintCLI's `--risk` line
- files: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/pd-lint, plugins/pd/scripts/test_pd_common_stage.py
- uses: plugins/pd/scripts/conftest.py
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_pd_common_stage.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B7] (fixture: pd_repo): STAGES is ("mvp", "production"); load_config gives stage "production" for a config without the key and "mvp" for one with `stage: mvp`; item_stage({}) is "production" and item_stage({"stage": "mvp"}) is "mvp".
  - C2 [B7] (fixture: pd_repo): with config `stage: mvp`, item_stage of a README frontmatter that has no stage key is still "production": the README decides, never the config default.
  - C3 [B49] (fixture: none): ISSUE_RE matches `- R3 warning harden-later shape.md:12 — edge case deferred` with groups id R3, sev warning, cat harden-later, file shape.md, line 12, claim `edge case deferred`; and matches `- R1 blocker src/a.py:3 — wrong exit` with cat absent, file src/a.py, line 3.
  - C4 [B49] (fixture: none): open_blockers over one review entry holding both lines of C3 returns exactly one blocker, R1, with file src/a.py and line 3; the harden-later warning is neither a blocker nor read with `harden-later` as its file.
  - C5 [B19] (fixture: pd_repo): risk_signals(root, "HEAD~1..HEAD") after a commit adding `@app.get('/x')` as line 1 of src/pkg/api.py returns [("security", "src/pkg/api.py", 1)]; the same line added under the artifacts root, under a test path, or in a file named `café.py` (whose diff header git quotes) returns [].
  - C6 [B20] (fixture: none): risk_waivers returns {"security"} for a decision entry holding `Risk: none (security) — the matches are pd's own message text`, and an empty set for `Risk: none (security)` with no reason, for `Risk: none (perf) — x`, and for the C6 waiver line inside a note entry.
  - C7 [B19] (fixture: pd_repo): base_branch returns "develop" for config `base_branch: develop`; for `auto` in a repo with no remote, "main"; for `auto` in a clone of a repo whose HEAD branch is "trunk", "trunk".
  - C8 [B19, B20] (fixture: pd_repo): after C5's commit, `pd-lint --risk HEAD~1..HEAD` prints `pd-lint: WARN <root>/src/pkg/api.py:1: risk signal (security) and the work item has no risk: [security] tag: set it, or the user clears it with a decision entry`, the text it prints today; once a decision entry holding C6's waiver line is committed to the work item's log, the same command prints no WARN.
  - C9 [B7, B49] (fixture: none): `python3 plugins/pd/scripts/pd_common.py --self-test` and `plugins/pd/scripts/pd-lint --self-test` each exit 0.

#### Task 2: simple_commands in commit_target, and the shared hook fixtures [parallel-safe]
- contract: shape.md ## Design, SimpleCommands; Test strategy, `plugins/pd/hooks/conftest.py`
- files: plugins/pd/hooks/lib/commit_target.py, plugins/pd/hooks/lib/test_commit_target.py, plugins/pd/hooks/conftest.py
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/lib/test_commit_target.py --junitxml=agent_sandbox/junit/task-2.xml`
- junit: agent_sandbox/junit/task-2.xml
- test cases:
  - C1 [B38] (fixture: none): simple_commands("git log | grep x", d) returns [(["git", "log"], d), (["grep", "x"], d)].
  - C2 [B52] (fixture: none): simple_commands('git commit -m "never rm -rf /"', d) returns one command, ["git", "commit", "-m", "never rm -rf /"]; no returned command starts with "rm".
  - C3 [B52] (fixture: none): for `cd sub && rm -rf build; cd .. && git status`, the rm command runs in d/sub and git status in d.
  - C4 [B52] (fixture: none): `env FOO=1 sudo -u me git push -f origin x` yields ["git", "push", "-f", "origin", "x"]; `git push -f >out 2>&1` yields ["git", "push", "-f"], its redirections dropped.
  - C5 [B40] (fixture: none): an unclosed quote, `git push "x`, returns None.
  - C6 [B38] (fixture: none): `bash -c "cat f"` returns the one command ["bash", "-c", "cat f"], the -c script not recursed; `echo $(cat f)` returns no command whose first word is cat.
  - C7 [B54] (fixture: none): a heredoc, `cat <<EOF`, newline, `rm -rf /`, newline, `EOF`, returns only the cat command; `( git add . ) && git commit -m x` returns ["git", "add", "."] and ["git", "commit", "-m", "x"].
  - C8 [B52] (fixture: none): importing commit_target in a fresh `python3 -c` with empty stdin prints nothing and exits 0, so main runs only under `__name__`; `bash plugins/pd/hooks/tests/test-pd-commit-lint.sh` exits 0, so scan() and pd-commit-lint.sh's call are unchanged.
  - C9 [B52] (fixture: run_hook, gate_home): run_hook(plugins/pd/hooks/pd-commit-lint.sh, a Bash payload `git status` whose cwd is a non-git temporary directory) returns exit 0 and empty stderr, and gate_home's HOME holds `.claude/pd/gate/` as an empty directory.

#### Task 3: the pd-yolo and pd-pr-checks scripts [parallel-safe]
- contract: shape.md ## Design, YoloCLI; SessionState (the `.yolo` file); PrChecksCLI
- files: plugins/pd/scripts/pd-yolo, plugins/pd/scripts/pd-pr-checks, plugins/pd/scripts/test_pd_yolo.py, plugins/pd/scripts/test_pd_pr_checks.py
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_pd_yolo.py plugins/pd/scripts/test_pd_pr_checks.py --junitxml=agent_sandbox/junit/task-3.xml`
- junit: agent_sandbox/junit/task-3.xml
- test cases:
  - C1 [B24] (fixture: none): with HOME a temporary directory, `pd-yolo on --session s1` prints "on", exits 0 and creates HOME/.claude/pd/gate/s1.yolo holding one line that parses as a local ISO time; `pd-yolo status --session s1` then prints "on".
  - C2 [B60] (fixture: none): after C1, `pd-yolo off --session s1` prints "off" and removes s1.yolo; status prints "off"; a second off prints "off" and exits 0.
  - C3 [B51] (fixture: none): with s1 on, `pd-yolo status --session s2` prints "off", and no s2 file exists in HOME/.claude/pd/gate/.
  - C4 [B24] (fixture: none): `--session '${CLAUDE_SESSION_ID}'`, `--session ../x` and `--session ''` each exit 2 with stderr `pd-yolo: bad session id <sid>`; the listing of HOME/.claude/pd/gate/ is the same before and after.
  - C5 [B24] (fixture: none): `pd-yolo --self-test` exits 0.
  - C6 [B55] (fake: gh): buckets pass and skipping -> `pd-pr-checks 7` exits 0 and prints the fake's JSON list of {name, bucket}.
  - C7 [B55] (fake: gh): one fail bucket among passes, with gh exiting 0 as it does under --json -> exit 1, and stdout names the failing check; a cancel bucket -> exit 1.
  - C8 [B55] (fake: gh): the fake reports no checks -> exit 3, stdout empty.
  - C9 [B55] (fake: gh): the fake always reports pending -> `pd-pr-checks 7 --for 2` exits 8 in under 10 seconds; the exit is 8, not 2, though gh exited 8.
  - C10 [B55] (fake: gh): the fake reports no such PR -> exit 2, with `no pull requests found` on stderr.
  - C11 [B55] (fake: gh): pending on the first call and pass on the second -> `pd-pr-checks 7 --for 40` exits 0 after exactly two calls of the fake, printing the second call's list.
  - C12 [B55] (fixture: none): `pd-pr-checks --self-test` exits 0.

#### Task 4: severity `note` in the reviewer agents and their commands [parallel-safe]
- contract: shape.md ## Design, "Rename surfaces: suggestion to note" (B42; wording only, no contract block)
- files: plugins/pd/agents/security-reviewer.md, plugins/pd/agents/ds-analysis-reviewer.md, plugins/pd/agents/ds-code-reviewer.md, plugins/pd/agents/retro-facilitator.md, plugins/pd/commands/review-ds-code.md, plugins/pd/commands/review-ds-analysis.md, plugins/pd/scripts/test_severity_note.py
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_severity_note.py --junitxml=agent_sandbox/junit/task-4.xml`
- junit: agent_sandbox/junit/task-4.xml
- test cases:
  - C1 [B42] (fixture: none): the search `grep -nE 'blocker \| warning \| suggestion|\| suggestion \|'` over security-reviewer.md, ds-analysis-reviewer.md and ds-code-reviewer.md finds nothing, and every severity enum in those files reads `blocker | warning | note`, with ds-analysis-reviewer.md holding two.
  - C2 [B42] (fixture: none): retro-facilitator.md holds `blocker vs warning vs note` and not `blocker vs warning vs suggestion`.
  - C3 [B42] (fixture: none): the severity lists in review-ds-code.md and review-ds-analysis.md say `List notes` where they said `List suggestions`.
  - C4 [B42] (fixture: none): each of the three reviewer agents still has the fix-text field `"suggestion": "How to fix it"` in its output schema, so only severities changed.
  - C5 [B42] (fixture: none): every hit of `grep -rnE 'suggestion' plugins/pd/agents plugins/pd/commands` is a fix-text field (`"suggestion":`), or the `Feature suggestion` prose in design-reviewer.md and plan-reviewer.md that shape.md "Rename surfaces" leaves as is.
  - C6 [B42] (fixture: none): `./validate.sh`, run from the repository root, exits 0.

### Wave 2

#### Task 5: the YOLO guard hook [parallel-safe]
- contract: shape.md ## Design, YoloGuard; HookInput; SessionState
- files: plugins/pd/hooks/pd-yolo-guard.sh, plugins/pd/hooks/tests/test_pd_yolo_guard.py
- uses: plugins/pd/hooks/lib/commit_target.py, plugins/pd/scripts/pd_common.py, plugins/pd/hooks/conftest.py, plugins/pd/scripts/pd-yolo
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/tests/test_pd_yolo_guard.py --junitxml=agent_sandbox/junit/task-5.xml`
- junit: agent_sandbox/junit/task-5.xml
- test cases:
  - C1 [B28] (fixture: run_hook, gate_home): YOLO off: AskUserQuestion asking `Pick a name?` and Bash `git push -f origin x` are each allowed; a `python3` placed first on PATH that creates a file when run is never run, because the fast path is bash.
  - C2 [B26] (fixture: run_hook, gate_home): YOLO on: AskUserQuestion with the questions `Hard stop: merge?` and `Pick a name?` is refused; stderr holds `decide this yourself`, `A (conductor, on the user's behalf):` and each of Session:, Stage:, Pros/cons:, Trade-off:, Implications: and Premortem:.
  - C3 [B27] (fixture: run_hook, gate_home): YOLO on: AskUserQuestion whose every question starts `Hard stop:` is allowed.
  - C4 [B28] (fixture: run_hook, gate_home): s1.yolo exists and the call's session_id is s2: AskUserQuestion asking `Pick a name?` is allowed, while the same call as s1 is refused.
  - C5 [B60] (fixture: run_hook, gate_home): after `pd-yolo off --session s1` under the same HOME, C2's call is allowed.
  - C6 [B40] (fixture: run_hook, gate_home): YOLO on: AskUserQuestion whose tool_input.questions is a string exits 0, with stderr exactly the one line `pd-yolo-guard: check failed; question allowed`.
  - C7 [B52, B53] (fixture: run_hook, gate_home): YOLO on, base branch main, on branch workitem/x: each of `git push -f origin x`, `git push --force-with-lease=x origin x`, `git push origin +x`, `git push --delete origin x`, `git push origin :x`, `git push origin main`, `git push origin HEAD:refs/heads/main`, `git push --all origin`, `gh pr merge 3 --squash`, `git branch -D x`, `git branch -d x`, `git branch --delete x`, `git reset --hard HEAD~1`, `git clean -fd`, `git clean --force`, `rm -rf /tmp/elsewhere`, `git -C other push -f origin x`, `cd sub && git push -f origin x` and `git status && git push -f` is refused, with stderr quoting the refused simple command and holding `Hard stop:`, `! ` before the command, and `Never run it yourself`.
  - C8 [B52] (fixture: run_hook, gate_home): YOLO on, on branch main: `git push` with no refspec and `git push origin HEAD` are refused; on branch workitem/x both are allowed.
  - C9 [B52] (fixture: run_hook, gate_home): YOLO on, on branch workitem/x, each is allowed: `git push -u origin workitem/x`, `git push -o ci.skip origin workitem/x`, `git commit -m "never rm -rf /"` in a clean repo, `rm -rf agent_sandbox/2026-11-26/x` at the repo top, `rm notes.txt`, `git branch -v`, `git clean -n`, `git reset --soft HEAD~1`.
  - C10 [B52] (fixture: run_hook, gate_home): YOLO on: `git worktree remove --force <w>`, for a worktree <w> on branch pd/2026-11-26-x/task-1, is allowed from the main checkout and from a sibling worktree on pd/2026-11-26-x/task-2; the same command for a worktree on branch feature/y is refused.
  - C11 [B52] (fixture: run_hook, gate_home): YOLO on, in a checkout made with `git init --separate-git-dir=<store>/.git`: `rm -rf <store>/agent_sandbox/x` is refused, while `rm -rf agent_sandbox/x` inside the checkout is allowed.
  - C12 [B54] (fixture: run_hook, gate_home): YOLO on, a repo mid-merge with the conflicted file f: `git commit -m x`, `git merge --continue`, and `git -C <that repo> commit -m x` run from another directory are each refused, with stderr naming f, `! git commit` and `pd-yolo off`; in a clean repo `git commit -m x` is allowed.
  - C13 [B40] (fixture: run_hook, gate_home): YOLO on: lines simple_commands can't split are refused with stderr `pd-yolo-guard: check failed; command refused while YOLO is on`, namely `git push -f "x`, `git p'ush' -f "x` and `echo $(git status) "x`, while `echo "hi` exits 0.
  - C14 [B52] (fixture: run_hook, gate_home): YOLO on: the payload of C7's first command with agent_id set, a subagent's call, is refused like the main session's.

#### Task 6: the main-session read-budget hook [parallel-safe]
- contract: shape.md ## Design, ReadBudget; HookInput; SessionState (the `.reads` file)
- files: plugins/pd/hooks/pd-read-budget.sh, plugins/pd/hooks/tests/test_pd_read_budget.py
- uses: plugins/pd/hooks/lib/commit_target.py, plugins/pd/scripts/pd_common.py, plugins/pd/hooks/conftest.py
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/tests/test_pd_read_budget.py --junitxml=agent_sandbox/junit/task-6.xml`
- junit: agent_sandbox/junit/task-6.xml
- test cases:
  - C1 [B33] (fixture: run_hook, gate_home): a repo with no pd config, and one whose config lacks main_read_budget: 10 Reads and a WebFetch are each allowed, and the listing of HOME/.claude/pd/gate/ shows no s1.reads.
  - C2 [B34] (fixture: run_hook, gate_home): `main_read_budget: 3`, main session: Reads 1 to 3 are allowed with s1.reads at 1, 2 and 3 bytes; the 4th is refused, stderr holding `4 reads this turn (budget 3)` and `pd:codebase-explorer`, and s1.reads holds 4 bytes.
  - C3 [B35] (fixture: run_hook, gate_home): budget 3, first call of the turn: WebFetch is refused with stderr naming `pd:internet-researcher`, and WebSearch the same; s1.reads holds 0 bytes or is absent.
  - C4 [B36] (fixture: run_hook, gate_home): budget 1, agent_id set: 5 Reads, a Grep and a WebFetch are each allowed, and s1.reads holds 0 bytes or is absent.
  - C5 [B37] (fixture: run_hook, gate_home): budget 1: 5 Reads of <repo>/docs/dev_artifacts/workitems/x/shape.md and 5 of $CLAUDE_PLUGIN_ROOT/skills/a/SKILL.md are allowed with s1.reads at 0 bytes; then a Read of <repo>/src/a.py leaves it at 1 byte.
  - C6 [B38] (fixture: run_hook, gate_home): budget 100: s1.reads grows by one byte for each of Grep, mcp__codegraph__codegraph_explore, and Bash `git log | grep x`, `cat f`, `/usr/bin/head f`, `find . -name x` and `rg x`; it grows by none for Glob, or for Bash `ls`, `git status`, `bash -c "cat f"` or `echo cat`.
  - C7 [B39] (fixture: run_hook, gate_home): budget 1 with s1.reads at 1 byte: a UserPromptSubmit event leaves it at 0 bytes, and the next Read is allowed.
  - C8 [B57] (fixture: run_hook, gate_home): budget 1, a work item README under docs/dev_artifacts/workitems/ whose `## Now` holds `run in flight: verify-change session s1`: 5 Reads and a WebFetch are each allowed; with that line naming session s2 instead, the 2nd Read and the WebFetch are refused.
  - C9 [B40] (fixture: run_hook, gate_home): budget 3: stdin that isn't JSON exits 0 with stderr exactly `pd-read-budget: check failed; call allowed`; with `main_read_budget: abc`, 10 Reads each exit 0 with one stderr line, and no s1.reads is written.
  - C10 [B34] (fixture: run_hook, gate_home): budget 100: 20 counted Reads started in parallel leave s1.reads at exactly 20 bytes.

#### Task 7: the Stop gate's goals, messages and turn reset [parallel-safe]
- contract: shape.md ## Design, StopGate; SessionState
- files: plugins/pd/hooks/pd-stop-gate.sh, plugins/pd/hooks/tests/test-pd-stop-gate.sh, plugins/pd/hooks/tests/test_pd_stop_gate_goals.py
- uses: plugins/pd/hooks/conftest.py, plugins/pd/scripts/pd_common.py
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/tests/test_pd_stop_gate_goals.py --junitxml=agent_sandbox/junit/task-7.xml`
- junit: agent_sandbox/junit/task-7.xml
- test cases:
  - C1 [B31] (fixture: run_hook, gate_home): a goal work item over its token cap is held (exit 2) with stderr holding `Ask the owner: Hard stop:`; a goal work item with no progress since the last hold, the same.
  - C2 [B32] (fixture: run_hook, gate_home): a goal work item at its target with no open blockers: stderr says to clear the goal: line and holds `YOLO stays on until pd-yolo off or the session ends.`
  - C3 [B56] (fixture: run_hook, gate_home): a brainstorm item, status active, whose `## Now` holds this session's goal line is held, with stderr `pd gate: goal <id> is a brainstorm; carry it to promotion. Promotion moves the goal line to the new work item.`; an rca item likewise names its type; a goal line naming another session doesn't hold the stop.
  - C4 [B56] (fixture: run_hook, gate_home): the brainstorm at status done, and the goal line moved to the work item promoted from it, at phase design and target finish: the stop is held with the work item's own goal message, naming the work item's id and not the brainstorm's.
  - C5 [B39] (fixture: run_hook, gate_home): s1.reads at 5 bytes: a held stop leaves it at 0 bytes; an allowed stop (no goal line) leaves it at 5.
  - C6 [B31, B32] (fixture: none): `bash plugins/pd/hooks/tests/test-pd-stop-gate.sh` exits 0, its message assertions moved to the new texts.

#### Task 8: stage in pd-new, pd-status and pd-init [parallel-safe]
- contract: shape.md ## Design, NewCLI; StatusCLI; ConductorProse's pd-init line
- files: plugins/pd/scripts/pd-new, plugins/pd/templates/README.md, plugins/pd/scripts/pd-status, plugins/pd/scripts/pd-init, plugins/pd/scripts/test_stage_new_status.py, plugins/pd/scripts/test_pd_status_leftovers.py
- uses: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/conftest.py
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_stage_new_status.py plugins/pd/scripts/test_pd_status_leftovers.py --junitxml=agent_sandbox/junit/task-8.xml`
- junit: agent_sandbox/junit/task-8.xml
- test cases:
  - C1 [B1] (fixture: pd_repo): with config `stage: mvp`, `pd-new workitem "T"` writes a README whose frontmatter has `stage: mvp`.
  - C2 [B2] (fixture: pd_repo): with a config that has no stage key, and in a repo with no .claude/pd.local.md, the new README has `stage: production`.
  - C3 [B3] (fixture: pd_repo): with config `stage: production`, `pd-new workitem "T" --stage mvp` writes `stage: mvp`.
  - C4 [B4] (fixture: pd_repo): `pd-new workitem "T" --stage beta` exits 2, with stderr naming mvp and production, and no new directory under the workitems root.
  - C5 [B5] (fixture: pd_repo): with config `stage: beta`, `pd-new workitem "T"` exits 1, with stderr starting `pd-new: refused:` and naming stage, mvp and production; no new directory.
  - C6 [B3] (fixture: pd_repo): `pd-new backlog "x" --stage mvp` is refused as `--mode` is on a backlog item, and backlog.md is unchanged.
  - C7 [B8] (fixture: pd_repo): with config `stage: production`, open work items at mvp and production, a done work item at mvp and a brainstorm: pd-status's header is `STATUS PHASE TYPE ID STAGE NOW`; the rows show `mvp*`, `production`, `mvp` without a star, and `-`; the table is followed by `* stage differs from the project default (production)`.
  - C8 [B7] (fixture: pd_repo): a work item README with no stage key shows `production` in the STAGE column with no star, and no footer is printed when no row differs.
  - C9 [B50] (fixture: none): `pd-init` on a temporary git repo with no .claude/pd.local.md writes a config whose frontmatter has `stage: production`.
  - C10 [B1, B8, B50] (fixture: none): `pd-new --self-test`, `pd-status --self-test` and `pd-init --self-test` each exit 0, pd-init's field set (`pd-init:146`) now including stage.

#### Task 9: stage, decision records, risk and probe rulings in pd-lint and phase-gate.sh [parallel-safe]
- contract: shape.md ## Design, LintCLI; GateCLI; LogEntries
- files: plugins/pd/scripts/pd-lint, plugins/pd/scripts/phase-gate.sh, plugins/pd/scripts/test-phase-gate.sh, plugins/pd/scripts/test_stage_lint_gate.py
- uses: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/conftest.py
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_stage_lint_gate.py --junitxml=agent_sandbox/junit/task-9.xml`
- junit: agent_sandbox/junit/task-9.xml
- test cases:
  - C1 [B6] (fixture: pd_repo): a work item README with `stage: beta` makes `pd-lint <dir>` print `pd-lint: ERROR <README>:<line>:` naming stage and beta, exit 1; `stage: mvp` gives no error.
  - C2 [B7] (fixture: pd_repo): a work item README with no stage key gives no pd-lint error; a brainstorm README with `stage: mvp` gives an ERROR, as `mode:` on a brainstorm does.
  - C3 [B29] (fixture: pd_repo): a decision entry answered `A (conductor, on the user's behalf):` holding only Session: and Stage: lines gives one ERROR naming Pros/cons:, Trade-off:, Implications: and Premortem:, exit 1; with all six lines, no error; the incomplete entry on a work item at status done still gives the ERROR.
  - C4 [B47] (fixture: pd_repo): a stage-mvp work item whose `## Requirements` holds a B1: line and no line starting `Deferred:` gives a WARN and exit 0; with `Deferred: none`, no WARN; a production work item without the line, no WARN.
  - C5 [B48] (fixture: pd_repo): a plan task with `proof: green-only (mvp)` gives no error at stage mvp; at stage production it gives the error `proof: green-only needs a reason`.
  - C6 [B15] (fixture: pd_repo): README stage mvp and phase verify, whose latest review entry with a Stage: line says production: `phase-gate.sh verify` prints `GATE FAIL [verify]: the review applied stage production; the work item is mvp`, exit 1; the same at phase design with `phase-gate.sh design`, and at create-plan.
  - C7 [B16] (fixture: pd_repo): at phase design, review entries without Stage: lines only (a calvin cycle, an old review) pass the design gate with no stage message; an older `Stage: production` entry followed by a newer `Stage: mvp` one, on an mvp item, passes too, since the latest decides.
  - C8 [B18] (fixture: pd_repo): a work item at phase implement, README stage mvp, whose design review says `Stage: production`: `pd-lint <dir>`, which replays the passed design and create-plan gates, reports no stage failure; with the README's phase set back to design, `phase-gate.sh design` fails on the stage.
  - C9 [B19] (fixture: pd_repo): on a branch whose diff from main adds `@app.get('/x')` as line 1 of src/pkg/api.py, `phase-gate.sh verify` prints `GATE FAIL [verify]: security signal src/pkg/api.py:1: add risk: security or a Risk: none (security) decision`, for a standard and for an express work item.
  - C10 [B20] (fixture: pd_repo): the same diff with README `risk: [security]`, or with a decision entry holding `Risk: none (security) — the match is message text`, passes the risk check: no risk message in the output.
  - C11 [B30] (fixture: pd_repo): a sign-off answered `A (conductor, on the user's behalf):` with `Session: s1`, after a YOLO confirmation entry with `Session: s1`, passes `phase-gate.sh specify`; with the confirmation's `Session: s2`, with no confirmation, or with the confirmation after the sign-off, it prints `GATE FAIL [specify]`, exit 1.
  - C12 [B49] (fixture: pd_repo): an mvp work item at finish whose review entry holds `- R3 warning harden-later shape.md:12 — x` fails `phase-gate.sh finish` until backlog.md has a line ending `(from: workitems/<id>)` that holds that entry's reference with `#R3`.
  - C13 [B61, B43, B44] (fixture: pd_repo): a shape.md holding `B43: Probe:` and `B44: Probe:` lines fails `phase-gate.sh finish` with `the owner's ruling on B43 is missing or names no next step` until each has a decision entry with `A (user, verbatim): "Met …"`, `Ruling: B<n>` and `Next: none`; `"Missed …"` with `Next: none` fails; `"Missed …"` with `Next: phase finish -> design (back)`, or with `Next: backlog 2026-11-26-x`, passes.
  - C14 [B15, B19] (fixture: none): `plugins/pd/scripts/pd-lint --self-test` and `bash plugins/pd/scripts/test-phase-gate.sh` each exit 0.

#### Task 10: the review prompt, the stage bars, the review schema and verify-change's stage [parallel-safe]
- contract: shape.md ## Design, ReviewPromptCLI; StageBars; ReviewSchema; VerifyArgs
- files: plugins/pd/scripts/pd-review-prompt, plugins/pd/references/stage-bars.md, plugins/pd/references/workflow-results.md, plugins/pd/workflows/verify-change.js, plugins/pd/workflows/tests/test-workflows.mjs, plugins/pd/scripts/test_pd_review_prompt.py, plugins/pd/workflows/tests/test_workflows_node.py
- uses: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/conftest.py, plugins/pd/skills/verifying/SKILL.md, plugins/pd/skills/designing/SKILL.md, plugins/pd/skills/planning/SKILL.md
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_pd_review_prompt.py plugins/pd/workflows/tests/test_workflows_node.py --junitxml=agent_sandbox/junit/task-10.xml`
- junit: agent_sandbox/junit/task-10.xml
- test cases:
  - C1 [B9] (fixture: pd_repo): README stage mvp: `pd-review-prompt verifying <dir>` exits 0, and stdout is, in order, the exact line `Stage: mvp`, verifying SKILL.md's `## Review checklist` section verbatim with its heading, stage-bars.md's `## mvp` section verbatim, the line `Return only a JSON object matching this schema.`, and the json block under workflow-results.md's `## The review call` verbatim.
  - C2 [B10] (fixture: pd_repo): README stage production: line 1 is `Stage: production`, the `## production` section is present, and no line of the `## mvp` section's paragraph is.
  - C3 [B7] (fixture: pd_repo): a README with no stage key: line 1 is `Stage: production`.
  - C4 [B11] (fixture: pd_repo): `pd-review-prompt designing planning <dir>`: both checklists, designing's then planning's, with exactly one stage section and one schema block.
  - C5 [B12] (fixture: pd_repo): the skill `brainstorming`, which has no `## Review checklist`, and a directory without README.md each exit 1 with stderr starting `pd-review-prompt:` and empty stdout; no arguments exit 2.
  - C6 [B9] (fixture: none): stage-bars.md's only `## ` headings are `## mvp` and `## production`; the mvp paragraph names harden-later and each item never relaxed: the security review for risk: security, R0, QB<n>, the token budget, and validation at trust boundaries.
  - C7 [B13] (fake: test-workflows.mjs runtime stubs): verify-change with no stage, with stage "beta", and with stage "mvp" but a checklist whose first line is `Stage: production` each throw an error naming the arg, with no agent call recorded.
  - C8 [B14, B45] (fake: canned reviewer, QA and fixer replies): a run with stage "mvp" and a checklist starting `Stage: mvp` returns a result whose stage is "mvp", as is its review's; when the reviewer gives no usable review, the fallback review's stage is "mvp".
  - C9 [B41] (fake: test-workflows.mjs runtime stubs): REVIEW equals the json block found under the `## The review call` heading, with keys unordered and required compared as a set; removing stage from the markdown copy only, or changing the severity enum on one side only, makes the comparison fail naming both files.
  - C10 [B14] (fake: test-workflows.mjs runtime stubs): RESULT's keys equal those of the verify-change block in workflow-results.md, both including stage.
  - C11 [B13, B41] (fixture: none): `node plugins/pd/workflows/tests/test-workflows.mjs` exits 0; this is test_workflows_node.py's case, and C7 to C10 run inside it.
  - C12 [B9] (fixture: none): `pd-review-prompt --self-test` exits 0.

### Wave 3

#### Task 11: the conductor prose for the entry point, YOLO, stages and the review call [parallel-safe]
- contract: shape.md ## Design, ConductorProse; LogEntries
- files: plugins/pd/commands/secretary.md, plugins/pd/commands/init.md, plugins/pd/skills/workflow-transitions/SKILL.md, plugins/pd/skills/specifying/SKILL.md, plugins/pd/skills/planning/SKILL.md, plugins/pd/skills/verifying/SKILL.md, plugins/pd/skills/finishing-branch/SKILL.md, plugins/pd/references/review-call.md, plugins/pd/references/log-entries.md, plugins/pd/scripts/test_yolo_prose.py
- uses: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/pd-yolo, plugins/pd/scripts/pd-review-prompt, plugins/pd/scripts/pd-pr-checks
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_yolo_prose.py plugins/pd/scripts/test_worktree_callers.py plugins/pd/scripts/test_explorer_codegraph.py --junitxml=agent_sandbox/junit/task-11.xml`
- junit: agent_sandbox/junit/task-11.xml
- test cases:
  - C1 [B21, B22] (fixture: none): secretary.md says that once the work item exists, without YOLO, one AskUserQuestion offers a goal run to finish; on yes it writes `goal: <id> target finish session` with the session id and commits it before Criteria starts; on no it writes no goal line.
  - C2 [B23] (fixture: none): secretary.md says that at stage mvp, from the config or `--stage`, the risk tags security and migration are the only standard-depth triggers, and that the triage entry cites `stage: mvp`.
  - C3 [B59] (fixture: none): secretary.md's argument-hint holds `[--yolo]` and `[--stage mvp|production]`, and its text passes `--stage` through to create-workitem.
  - C4 [B24, B25] (fixture: none): secretary.md's `--yolo` step invokes workflow-transitions' YOLO section before triage. That section asks `Hard stop: turn YOLO on for this session?`, runs `pd-yolo on --session ${CLAUDE_SESSION_ID}` and then `pd-yolo status --session ${CLAUDE_SESSION_ID}`, which must print `on`, and on no carries on without YOLO.
  - C5 [B24, B51] (fixture: none): the YOLO section writes the confirmation entry before the session's first entry in any item's log, then the decisions made before that item existed; log-entries.md's confirmation shape holds `Q: Hard stop: turn YOLO on for this session?`, an `A (user, verbatim):` quote starting Yes, and `Session: <session id>`.
  - C6 [B26, B29] (fixture: none): the six labels of pc.DECISION_RECORD appear, in its order, in log-entries.md's decision-record shape, in workflow-transitions' YOLO section and in its print-mode line (`workflow-transitions/SKILL.md:49`).
  - C7 [B60] (fixture: none): the YOLO section runs `pd-yolo off --session ${CLAUDE_SESSION_ID}` when the owner says to turn YOLO off.
  - C8 [B56] (fixture: none): the YOLO section says that promotion moves this session's goal line from the brainstorm or rca to the new work item.
  - C9 [B17, B18, B46] (fixture: none): workflow-transitions' stage-change rule says: a decision entry and the README's `stage:` edited, committed first; mvp to production past specify moves back to specify with `Invalidates:`; production to mvp moves nothing back, and at finish it makes a review call with `pd-review-prompt verifying <dir>` before the finish gate; a done item is refused, proposing a new production work item from its harden-later backlog line.
  - C10 [B53] (fixture: none): the YOLO section says that a command the guard refused goes into a `Hard stop:` question showing it, that the owner runs it as `! <command>`, that the conductor never runs it itself, and that an agent's reported refusal becomes such a question.
  - C11 [B45] (fixture: none): review-call.md builds the prompt from `pd-review-prompt <skill> <work item dir>`, and its review entry copies the reply's stage into a `Stage:` line; log-entries.md's review entry shows the `Stage:` line and the issue line's optional ` harden-later` token; verifying passes `stage` and the pd-review-prompt output as checklist to verify-change.
  - C12 [B30, B47, B48] (fixture: none): specifying holds the mvp edge-case rule (a closing `Deferred:` line, judged at the sign-off, by the conductor under YOLO) and the YOLO sign-off with its decision record; planning allows `proof: green-only (mvp)` at stage mvp.
  - C13 [B55] (fixture: none): finishing-branch, under YOLO, opens the pull request with `git push -u origin workitem/<id>` and then `gh pr create`.
  - C14 [B55] (fixture: none): finishing-branch, under YOLO, waits with `pd-pr-checks <pr>` at a Bash timeout of 600000 ms, repeated while it exits 8, at most 7 times; exits 0 and 3 end the wait, 1 starts the fix cycles (at most 3, each fix with a decision record), and 2 asks `Hard stop: gh failed`.
  - C15 [B55] (fixture: none): finishing-branch, under YOLO, asks `Hard stop: checks still failing` after the third fix cycle, then `Hard stop: ready to merge?`, where yes runs `pd-yolo off --session ${CLAUDE_SESSION_ID}` before `gh pr merge`, and no clears the goal line and runs the same `pd-yolo off`.
  - C16 [B55] (fixture: none): finishing-branch, under YOLO with no remote or no `gh`, asks `Hard stop: branch ready; no remote to open a pull request on`.
  - C17 [B49] (fixture: none): finishing-branch writes a stage-mvp item's harden-later backlog line, ending `(from: workitems/<id>)`, before step 6.
  - C18 [B50] (fixture: none): init.md asks mvp or production through AskUserQuestion, then sets the config's stage key to the answer.
  - C19 [B43, B44, B61] (fixture: none): log-entries.md's probe-ruling shape holds `Ruling: B<n>` and `Next: none (Met only) | phase <from> -> <to> (back) | backlog <id>`.
  - C20 [B31, B34, B35] (fixture: none): workflow-transitions' hard-stop line requires the `Hard stop:` prefix, and its Dispatch line lets codebase-explorer, internet-researcher, investigation-agent and skill-searcher be dispatched at any stage.
  - C21 [B55] (fixture: none): `bash plugins/pd/hooks/tests/test-hooks.sh` and `./validate.sh` each exit 0; test_worktree_callers.py and test_explorer_codegraph.py, which read finishing-branch and planning, pass in the same command.

#### Task 12: hook registration, CI and the docs [parallel-safe]
- contract: shape.md ## Design, Test strategy "Cross-file invariants"; Requirements Scope In, "Docs sync"
- files: plugins/pd/hooks/hooks.json, .github/workflows/ci.yml, README.md, README_FOR_DEV.md, plugins/pd/README.md, docs/dev-guide/hook-development.md, docs/dev-guide/getting-started.md, docs/dev-guide/commands-reference.md, docs/technical/api-reference.md, docs/technical/architecture.md, plugins/pd/scripts/test_registration_docs.py
- uses: plugins/pd/hooks/pd-yolo-guard.sh, plugins/pd/hooks/pd-read-budget.sh, plugins/pd/scripts/pd-yolo, plugins/pd/scripts/pd-review-prompt, plugins/pd/scripts/pd-pr-checks
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_registration_docs.py --junitxml=agent_sandbox/junit/task-12.xml`
- junit: agent_sandbox/junit/task-12.xml
- test cases:
  - C1 [B26, B52] (fixture: none): hooks.json registers `${CLAUDE_PLUGIN_ROOT}/hooks/pd-yolo-guard.sh` under PreToolUse for the AskUserQuestion and Bash matchers.
  - C2 [B34, B39] (fixture: none): hooks.json registers pd-read-budget.sh under PreToolUse with the matcher `Read|Grep|Bash|WebFetch|WebSearch|mcp__codegraph__codegraph_explore`, and under UserPromptSubmit.
  - C3 [B41] (fixture: none): ci.yml's pytest line names each of the 13 test files this plan adds, and its self-test loop runs pd-yolo, pd-review-prompt and pd-pr-checks.
  - C4 [B33, B50] (fixture: none): getting-started.md's config table has a `stage` row (default production) and a `main_read_budget` row (default unset).
  - C5 [B26, B34] (fixture: none): README_FOR_DEV.md's hooks table and hook-development.md's hook table each name pd-yolo-guard.sh and pd-read-budget.sh; README_FOR_DEV.md's scripts line, architecture.md, api-reference.md and commands-reference.md's self-test loop each name pd-yolo, pd-review-prompt and pd-pr-checks; plugins/pd/README.md's hook count equals the number of distinct scripts hooks.json registers.
  - C6 [B24, B59] (fixture: none): README.md's secretary rows document `--yolo` and `--stage mvp|production`.
  - C7 [B26] (fixture: none): `bash scripts/check-doc-drift.sh` and `./validate.sh`, run from the repository root, each exit 0.
