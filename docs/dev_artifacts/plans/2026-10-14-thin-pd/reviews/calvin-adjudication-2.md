# Author's adjudication of calvin's second ledger (2026-10-14)

Author: the agent session that wrote the plan. Line numbers are ledger-2's (L1–L1142).

**Verdicts:**
- **R:** resolved; the plan changes as stated.
- **R0:** resolved by this answer; no plan change.
- **R (user):** settled by the user's ruling.

**The user's rulings this round (D17, verbatim):**
- **#18:** "Drop the token test".
- **#22:** "delete straight away if there is no use for them in the new implementation".

| # | Verdict | Author's answer (and the plan change) |
|---|---|---|
| 1 | R | **Per entry:**<br>a request: `pd-new feature` at Triage makes the feature directory;<br>an idea: `pd-new brainstorm`, one file;<br>a bug: `pd-new rca`, one file.<br>**Promotion:** a brainstorm or rca becomes a feature through `pd-new feature --from <item>`, at Criteria. An RCA's fix may run express straight after the RCA, through the same command with `mode: express`.<br>**The feature directory first exists** when `pd-new feature` runs. Rows 0 and 1 say so. |
| 2 | R | pd ships a `calvin-runner` agent: tools `Read`, `Glob`, `Skill`, plus `Write` for its ledger only (#46). It runs the user's `calvin` skill and writes the ledger to a file. `/pd:init` checks the skill is installed. Count: 21 kept plus 2 new (`merger`, `calvin-runner`). |
| 3 | R | **List every asking stop in two groups.**<br>**Hard stops:** a merge conflict, a cap reached, a judgement finding with no testable check, the token cap, the stuck path, a criterion nobody can state as an observable outcome, and the criteria sign-off (the user's own judgement). In print mode, a hard stop ends the run with a `handoff` entry.<br>**Decisions:** rejection batches, the workflow cap's "continue", a small overrun. In print mode, the conductor makes these on the user's behalf and logs each one (D16). For the workflow cap, that decision is "stop". |
| 4 | R | At `create-plan`, `pd-lint` takes wave n's base to be the current HEAD plus the file sets of every task in earlier waves. A `uses:` module must exist at HEAD, or be in the file set of this task or of an earlier wave's task. |
| 5 | R | The rule from #33 is refined. In the first commit, an existing source file may only gain lines (new signatures that raise); no existing line may change or go. That is checked mechanically: the diff on an existing source file is additions only. A lazy stub is still caught by the greens list. |
| 6 | R | The `qa` entry records the commit it ran against. `phase-gate.sh verify` requires no source or test file to have changed since that commit; later commits may touch only `log.md` and the README. |
| 7 | R | The `finishing` skill dispatches `pd:security-reviewer` directly, on Anthropic models, never Codex, per the user's CLAUDE.md. Add it to #7's list of single agents the conductor may dispatch. |
| 8 | R | This is an exception to #24's rule, and is stated as one. A security blocker re-runs only Verify's fix loop, the QA battery and the security reviewer's scoped re-check. The code review doesn't run again. |
| 9 | R | Express goes back to its earliest skipped stage. A small feature goes back to Contracts, at standard depth: Contracts and Plan get separate review calls. |
| 10 | R | Defaults when `/pd:init` was never run:<br>**`source_paths` and `test_paths`:** `src/` and `tests/` when present; otherwise the isolation checks skip with a warning.<br>**`languages`:** detected from file extensions.<br>**`qa_battery`:** has no default. `phase-gate.sh verify` fails with "set qa_battery in .claude/pd.local.md".<br>"pd works on defaults" is qualified accordingly. |
| 11 | R | Every task runs in its own worktree on its own branch, `pd/<feature id>/task-<n>`. "Sequential" only means one at a time, after the wave's parallel tasks land. The no-worktree special case goes, and resume, fix cycles and the merger treat every task alike. |
| 12 | R | Before a fix cycle, the workflow removes the failed attempt's worktree. The branch stays, and the fix agent checks it out. |
| 13 | R | The conductor clears the `goal:` line only when the user says stop, at any stop. "Continue" keeps the line and raises the budget. Fix the clearing rule (L218). |
| 14 | R | Reaching the target means: for `finish`, the feature is `done`; for any other phase, that phase's exit check has passed and `phase` has moved past it. |
| 15 | R | The gate counts usage on every stop, whether or not a goal runs. It charges the feature whose branch is checked out (the README's `branch:`). It blocks only while a matching `goal:` line exists. #44's rule changes accordingly. |
| 16 | R | Under D17, a component is kept if the new design uses it, and everything else is deleted straight away. `updating-docs` is used (§3, §3.1), so it's kept: add it to §A6. Kept commands are those §A6 names or a kept playbook calls; the §16 inventory lists them. |
| 17 | R | A check whose event doesn't occur naturally is provoked by a probe and recorded as such: a scripted AskUserQuestion hard stop, a deliberately flaky fixture, a small `feature_token_budget` for one probe run (#19). |
| 18 | R (user) | "Drop the token test". Success: every §A7 check passes and every question is answered, then the next five real features run with `pd-lint` clean and no registry. Tokens are recorded and decide nothing. Remove the 2× comparison from §A7 item 6, §16 and D16's text. |
| 19 | R | One probe run with a small `feature_token_budget` shows the gate ending a goal run at the cap (#17). The main bake-off run keeps no feature budget. |
| 20 | R | `pd-lint` reads `mode: express` from the frontmatter. For express, the mini-spec check (a task block in `shape.md` `## Requirements`) replaces the exit checks of specify, design and create-plan. |
| 21 | R | Adopt step 2 reads each `.meta.json`, and the same commit deletes it, as with the review files. |
| 22 | R (user) | "delete straight away if there is no use for them in the new implementation". A new §16 step at the start of the build, after the inventory, deletes every component the new design doesn't use, as one commit the user reviews. Git history keeps them. A failed rollout is fixed forward, or restored from history. Remove "the deletions wait" from §A7 and §16; D15's deferral of deletions is superseded (D17), while `--compare` stays deferred. |
| 23 | R | The provenance is the annex copy, `calvin-applied.md`. Add it to the annex list, and point D16 at it. The second ledger and this adjudication join the annex. |
| 24 | R | The plan, the annex and the essay are committed before the build starts, at a new §16 step after calvin, with the user's go. Adopt (step 5) later moves them. Fix L39 and L1137. |
| 25 | R | A plan may have a sibling directory with the same id, holding its annex: `plans/<id>/` beside `plans/<id>.md`. `pd-lint` accepts it and checks nothing inside it. Add to §3. |
| 26 | R | Cite as "§N, *title*" everywhere, including the §A8.2 table, using the essay's actual titles. |
| 27 | R | Reword: the gates caught every recorded occurrence; whether the rules prevented others can't be seen. |
| 28 | R | The author regenerates it after editing the `.mmd`: `mmdc -i docs/workflow-canonical.mmd -o docs/workflow-canonical.png -s 3 -b white`. Not committed. |
| 29 | R | `/pd:secretary`'s depth rules, applied by the conductor when `pd-new feature --from` promotes the item. L689 and L705 read "set at Triage, or at promotion for work that entered at Clarify". |
| 30 | R | `pd-new feature --from <brainstorm or rca> --plan <plan> <slug> "<title>"`. `--from` names the origin, and `--plan` the roadmap whose `planned:` line it fills. |
| 31 | R0 | Most of calvin's questions are about the text, which the conductor wrote. Questions about intent go to the user, and the user then signs off. Without the conductor's step, the user would answer every question. |
| 32 | R | The planner is the conductor, writing `plan.md`. Reword L69. |
| 33 | R | Up to three cycles, counted once for the joint review. |
| 34 | R | A Criteria pass has no blocker when calvin's ledger has no blocker-severity row. |
| 35 | R | Questions about intent, scope, priorities or a ruling are the user's; questions about wording or consistency are the conductor's. The conductor decides which is which, and the ledger records whom each went to. |
| 36 | R | The QA re-run rejects that fix and the cycle counts as spent. The next cycle must bring the test. |
| 37 | R | Add `flakes[]` to each task in the `implement-tasks` result. |
| 38 | R | The conductor proposes rejections before code, with file:line evidence; they still go to the user. |
| 39 | R | The `decision` entry written after the question names the `capped` entry it answers (`answers: capped@<date> <time>`), and `pd-status` links them. Reword #15's text. |
| 40 | R | They go to the next stage that has a reviewer (Verify's code review). At Finish, open ones are listed for the user in the finish summary. |
| 41 | R | Verify's fixer follows Execute's ladder: cycle 1 on sonnet, cycles 2 and 3 on the strongest model. |
| 42 | R0 | Small exists by the user's ruling (S1, D11): one sitting and one joint review for two artifacts. Without it, a short-plan feature pays two review calls. |
| 43 | R | Triage's reason for small goes in Triage's own entry (`phase triage -> <first stage>`). An overrun is a `note` entry, not a `phase` entry. |
| 44 | R | Unfamiliar to the codebase: no existing module or earlier feature covers the area. Triage judges, and records why. |
| 45 | R | Re-confirm only when the backward move changed nothing the plan cites (no contract or expectation it names); otherwise regenerate. |
| 46 | R | A `PreToolUse` hook on `Write` and `Edit`, keyed on `agent_type`, limits `calvin-runner` to its ledger path. The merger has no `Write` or `Edit`; its git runs through Bash, which can't be limited by pattern. That is accepted and stated. |
| 47 | R | The stage skill reads its own checklist section when it builds the review prompt, at dispatch. The bar still lives only in the skill. |
| 48 | R | Reword: "the strongest model runs the verifiers, the retro, and cycles 2 and 3 of executors and fixers". |
| 49 | R | Expand every "…/" source to its full URL (`https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/...`). |
| 50 | R | Every workflow result carries `stopped` (null or `"budget"`) plus its partial results. Add to the shared schema. |
| 51 | R | Each `rca-fanout` finding carries `verdict: survived \| refuted`. |
| 52 | R | `rca-fanout` runs for every bug that reaches Clarify, unless the cause is already known (then express, or Criteria). |
| 53 | R | The conductor relaunches `implement-tasks` with a resume list, and its `merger` merges the earlier run's passing branches first. Fix L823. |
| 54 | R | The conductor marks it at Plan, and the test-case review sees it. |
| 55 | R | `phase` moves back to `create-plan`. Merged tasks stay merged, tasks not yet run wait, and after the plan regenerates, tasks whose contract or cases changed run again. |
| 56 | R | When the toggle is off, the review call goes straight to the Claude reviewer. |
| 57 | R | Verify ends when the review has no blocker AND QA passes. "A pass with no blocker ends the stage" applies to pre-code stages only; say so. |
| 58 | R | `budget_increment` is the field, and its default is `feature_token_budget`. Fix #40's text to name the field. |
| 59 | R | Qualify: L239 "an unattended goal run"; L823 "workflow run". |
| 60 | R | Raised by `workflow_output_cap` again, recorded in a `decision` entry. The committed config doesn't change. |
| 61 | R | `internet-researcher` or `codebase-explorer`. Add `internet-researcher` to #7's list. |
| 62 | R | Remove "and the plan-mode hooks"; the inventory decides each hook. |
| 63 | R | The workflow results report `agents_used`, and the conductor writes it in each `run` entry; the bake-off sums them. Add to the schema. |
| 64 | R | Reclassify: §6 is compensating (it exists because weaker models are cheaper and weaker); §8 is structural (parallel agents can't share context). Fix the line. |
| 65 | R | The author decides: the downloads aren't kept, and sources are cited by full URL (#49). Add to D16's author calls. |
| 66 | R | Narrow it: every fact needed to resume lives in git, and audit facts do too from finish on, when `metrics` copies the token total in. |
| 67 | R0 | It serves the user's separate request for cheap, readable HTML of agent docs (§3.1, 2026-10-14). It isn't part of the topology; without it, docs stay markdown. |
| 68 | R | A backlog item isn't a frontmatter item. `pd-new backlog "<title>"` appends a dated line to `backlog.md`, and `pd-lint` checks the line format. Fix L636. |
| 69 | R | The merger runs `pd-lint` after each merge (part of step 4), and `/pd:finish-feature` runs it after the final merge. Fix #173's text. |
| 70 | R | Use real command names: `/pd:finish-feature`. Drop `/pd:resume`; commands accept any unique part of an id (`/pd:implement artifact-sop`). |
| 71 | R | Entry times carry the UTC offset: `## <date> <HH:MM±hh:mm> <kind>`. Sweep #181's format. |
| 72 | R | A converted entry carries a `Status: closed (legacy)` line, which `pd-status` treats as closed. Add to the entry shape and L900. |
| 73 | R | When two entries of the same kind share a minute, the second's heading gets a `-2` suffix, and references use it. |
| 74 | R | Drop "stops" from `metrics`; it's derivable from `decision` entries. `metrics` holds the mode and tokens. Sweep §6 and §A2. |
| 75 | R | The figures in the entry are the record. The cited raw log is a pointer, valid until cleanup. |
| 76 | R | The workflow's `journal.jsonl` in the session's transcript directory, valid while that directory exists. |
| 77 | R | `--sweep` matches a directory name that is either an item slug or a full id. |
| 78 | R | `pd-lint` accepts `issue: pending` with a warning; the user's next command creates the issue. |
| 79 | R | The value of `feature_token_budget` when the feature's first goal started, recorded in the gate's state file. If it's unset, there's no overrun trigger. |
| 80 | R | Among a wave's `[parallel-safe]` tasks. |
| 81 | R | Each contract block in `## Design` carries a `modules:` line, a pinned format, and the check reads those lines. Add it to the `shape.md` template. |
| 82 | R | At finish: after the retro if one runs, otherwise at the final merge. |
| 83 | R | §16 step 2 builds `pd-adopt` with the core scripts. |
| 84 | R | Adopt step 0 writes `sop: 1` and removes the retired fields, as its first change. |
| 85 | R | Detection keys on `sop: 1`, not on the file. If `pd.local.md` lacks `sop: 1` and `docs/dev_artifacts/workitems/` exists, say "run /pd:adopt". If the file is missing, offer `/pd:init`. |
| 86 | R | Only pedantic-drip's workspace rows (by its workspace uuid). Open rows stay unticked; closed rows are ticked with their recorded outcome. |
| 87 | R | Adopt step 0 makes the copy with SQLite's backup API, from an `immutable=1` source, of `entities.db` only, into `agent_sandbox/`. |
| 88 | R | Moot under D17: there's no old path left. A failure is fixed forward and logged as a `defect`. |
| 89 | R | Add a `pd-lint` check that every commit hash cited in `log.md` exists in the repository. Lint checks form; this adds one link to reality. |
