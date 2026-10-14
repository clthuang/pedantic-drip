# Author's adjudication of calvin's ledger (2026-10-14)

Author: the agent session that wrote `docs/plans/2026-10-14-thin-pd-native-design.md`. Line numbers are the ledger's (the plan as calvin read it, L1–L970).

**Verdicts:**
- **R:** resolved; the plan changes as stated.
- **R0:** resolved by this answer; no plan change.
- **D:** dismissed, with the reason.

**The user's rulings in this round (D16, verbatim):**
- **#203:** "Bake-off + 5 features (Recommended)".
- **#42:** "interactive only, when in print mode, any decisions made on user behalf should be logged".
- **#200:** "Committed (Recommended)".

| # | Verdict | Author's answer (and the plan change) |
|---|---|---|
| 1 | R | An inventory decides it. A new §16 build step, before Part A, lists every skill, command, agent and hook with its §A6 verdict. A component §A6 doesn't name retires unless that inventory shows it guards git or files without the registry. |
| 2 | R | Triage runs `pd-new` first, which creates the item with its README and `log.md`. Then it records `type`, `mode`, risk tags and skips. Say so in the Triage row. |
| 3 | R | Clarify's state lives in the brainstorm or rca single-file item. A feature directory exists from Criteria on, created by `pd-new feature --from <brainstorm or rca>`. Remove `brainstorm` from the feature `phase` vocabulary: `specify \| design \| create-plan \| implement \| verify \| finish`. |
| 4 | R | The success criteria ARE the `B<n>` behaviour expectations. Goals, non-goals and user stories are context for them. Reword row 2. |
| 5 | R | One Criteria cycle works like this. Calvin runs in report mode on the criteria, writing a ledger. The conductor answers each row, asking the user any question that is theirs, and revises. The next cycle re-runs calvin scoped to the earlier ledger's rows and the edit that answered them. There are at most three cycles. Replace "Calvin's own round cap is also three, so Criteria needs no extra rule." |
| 6 | R | A `decision` entry: "Q: criteria signed off? A (user, verbatim): …". `phase-gate.sh specify` (Criteria's exit check, see #8) requires it. |
| 7 | R | The rule allows two kinds of dispatch: pd's workflows, and the single named agents a playbook names. Those are calvin, `codebase-explorer`, the review call and `retro-facilitator`. Any other delegation breaks a conductor rule; no mechanism blocks it. Reword the delegation line. |
| 8 | R | `phase-gate.sh <phase>` is a phase's exit check: what it must hand down. The skill runs it before moving `phase:` past that phase. `pd-lint` runs it at commit for every phase before the current one, never the current one, so a mid-phase commit passes. Fix §5's `phase` row and §9. |
| 9 | R | It can't read them. Each task in `plan.md` gains a `uses:` list: the modules its tests or code import, written by the planner. `pd-lint` checks every `uses:` module exists at the wave's base or is in the task's own file set. |
| 10 | R | The plan groups tasks into waves. A wave's `[parallel-safe]` tasks run in worktrees from the feature branch's HEAD at the wave's start ("the base"), and the merger lands them in plan order. Then the wave's sequential tasks run one by one on the feature branch. Then the next wave. |
| 11 | R | Listed, not failed. A test already green at the first commit doesn't fail the merger's check; it is named for the Verify reviewer, since some are legitimately green. Sweep "every test … must fail" in the plan (L48), the essay §7, the canonical diagram, the principles diagram, and both decks' card 07: each test must fail as a test, and any already green is named. |
| 12 | R | The executor may not change its tests after the first commit. It reports which kind of error it found. A transcription error (the case is right, the code is wrong) restarts the task with a corrected first commit, and the merger re-checks red. A wrong test case sends the task back to Plan. |
| 13 | R | `.claude/pd.local.md` gains `qa_battery:`, the list of commands. `phase-gate.sh verify` requires a `qa` entry recording every battery command passing at the branch's HEAD, and no open blockers. |
| 14 | R | A blocker from the security review at finish sends the feature back to Verify, as a backward move. The fixer handles it under Verify's rules: a fresh budget of three fix cycles, and each fix brings its test. The security reviewer re-checks only its own findings, scoped like a pre-code re-review. |
| 15 | R | A `capped` entry closes the loop's open blockers, because the cap stop is an AskUserQuestion and the user's answer is a `decision` entry it points to. `pd-status` counts a blocker closed when a later `decision` or `capped` entry names it. |
| 16 | R | A task's first run is not a cycle. After a failed merger check come fix cycle 1 (sonnet), fix cycle 2 (strongest model) and fix cycle 3 (strongest model), then the user. Reword the two lines in §A2. |
| 17 | R | The fix agent starts in its own worktree and checks out the task's branch first; the prompt gives the branch name. §8's "can't pick up an earlier attempt's work" refers only to native isolation's starting point; reword it. |
| 18 | R | A judgement finding is a finding that behaviour is missing or wrong while the existing suite passes before and after its fix. A removal finding (over-engineering) is judged by the suite staying green, plus the diff removing the code at the finding's file:line. It never needs a new test and doesn't go to the user for that reason. |
| 19 | R | An unexpected result triggers a re-run. If the two runs disagree, a third run decides. The flaky test is logged in a `note` entry and becomes a QA finding in Verify. |
| 20 | R | Only the user accepts a rejection, before code and after, in the batch. Remove "or the next review" (L118, L792). |
| 21 | R | Express's mini-spec in `shape.md` `## Requirements` is one task block: the expectation, its test cases, the file set, `uses:` and the proving command. The implement args derive from it. |
| 22 | R | A risk tag set at Verify on a small or express feature is a backward move to the earliest skipped stage, which then runs at standard depth. A `phase` entry records it. |
| 23 | R | `pd-lint` checks `from_shape:` only while `phase` is `create-plan` or later. After a move back to `specify` or `design`, the stale plan is expected. Re-entering `create-plan` means regenerating the plan, or re-confirming it (#101). |
| 24 | R | A backward `phase` entry names what it invalidates. Review blockers about a replaced artifact close with that entry. Every stage from the moved-back one runs again: the plan regenerates, and tasks whose contract or test cases changed re-run. Code and merged branches are not marked stale mechanically. |
| 25 | R | Reviewers get `tools: Read, Grep, Glob`, with no Bash, Edit or Write; the diff and gate output arrive as inputs. Calvin's wrapper keeps `Write`, for its ledger file only. QA keeps Bash, since it runs suites. |
| 26 | R | Codex can't preload a Claude skill. The review call's prompt carries the stage's checklist inline, taken from the skill's checklist section. |
| 27 | R | **Merger:** a new agent, `merger` (git, `pd-proof`, read-only otherwise). **Fixer:** the `implementer` definition with a fixer brief, as a separate instance. **Refuter:** `rca-investigator` with a refute brief. Count: 21 kept plus 1 new. |
| 28 | R | Each workflow pins its result `schema` in its script, and `plugins/pd/references/workflow-results.md` restates them in one place. Fields: <br>**implement:** `tasks[{id, branch, head, case_map, proof:{first, head, greens, skipped}, cycles, status}]`, `stopped`, `tokens`. <br>**verify:** `review`, `qa`, `fixes[]`, `rejections[]`, `tokens`. <br>**research and rca:** `findings[{claim, evidence, source}]`, `tokens`. |
| 29 | R | A new `verifying` skill: it starts `verify-change` and writes the stage's entries. Add it to the phase skills. |
| 30 | R | The implementer renames its worktree branch to `pd/<feature id>/task-<n>` before committing, so a later session finds a run's branches by prefix. |
| 31 | R | "Sizeable" is the planner's call, recorded by the mark itself. The planner leaves `[parallel-safe]` off a task too small to pay for a worktree, and that task runs in sequence. |
| 32 | R | `### Test strategy` names the runner's JUnit option. A runner with none needs a JUnit reporter, added by an `infra` task before the first feature task. `pd-lint` requires each proving command to name a JUnit path. |
| 33 | R | It can't, across languages. The mechanical rule: the first commit may add new source files but may not modify existing ones. The per-test red check catches a lazy stub, because a test it makes green is named. "Signatures that raise" stays a brief rule. |
| 34 | R | The task just merged is charged. Its fix cycle gets both its own proof and the earlier proof it broke. |
| 35 | R | Each issue carries `{id, severity: blocker \| warning \| note, category, file, line, claim, evidence}`, pinned in `references/workflow-results.md`. |
| 36 | R | The line becomes `goal: <feature id> target <phase> session <session id>`. The gate acts only when the hook input's `session_id` matches. |
| 37 | R | The conductor clears the `goal:` line, and commits, in the turn where `pd-status` shows the target reached with no open blockers. |
| 38 | R | `## Now` opens with optional fixed key lines, `goal:` and `run in flight:`, followed by free text. Overwriting the section re-emits the key lines. `pd-lint` checks their format. |
| 39 | R | The target phase is on the `goal:` line (#36). Default: `finish`. |
| 40 | R | "Continue" writes a `decision` entry that raises the feature's budget by one more increment, the original amount again. The gate reads the latest raise. |
| 41 | R | "Moved" means a new commit on the feature branch, or `log.md` or the README changed, since the previous check. The gate keeps the previous check's state in `~/.claude/pd/gate/<session id>.json`. |
| 42 | R (user) | pd's conductor runs interactively. An unattended run is an interactive session left running under `/goal`, and a hard stop waits for the user. In print mode (`claude -p`) nothing can be asked: every decision the conductor makes on the user's behalf is a `decision` entry marked "A (conductor, on the user's behalf)", a hard stop ends the run with a `handoff` entry, and `--max-budget-usd` caps the run. `pd-status` lists on-behalf decisions for the user to review. |
| 43 | R | **Fields in `.claude/pd.local.md`:**<br>`workflow_output_cap`: output tokens per workflow run, compared with `budget.spent()`.<br>`feature_token_budget`: the gate's measure (#130), per feature.<br>`budget_increment`: the raise on "continue".<br>**Defaults:** set from the bake-off's measured spend. The bake-off runs with `workflow_output_cap` at 2M and no feature budget, and records its spend. |
| 44 | R | The gate charges usage to the feature whose `goal:` line is active. It records the session's total when the goal starts, and charges the difference. |
| 45 | R | There's no reliable session-end step. Each time it fires, the gate writes a running per-feature total to `~/.claude/pd/gate/<feature id>.json`; the next session continues it, and finish copies it into `metrics`. Whether a `SessionEnd` hook could do this goes on the bake-off list. |
| 46 | R | Not assumed. The conductor prints the next `/goal` command and the user starts it. Whether Claude can start a goal itself goes on the bake-off list (§A7). |
| 47 | R | The rollout stops at that item. Its plan section is revised and calvin'd, and the user decides. The deletions wait until every §A7 item passes. |
| 48 | R | **Second backward move:** two `phase` entries marked `(back)`. **Exhausted cycles:** a `capped` entry. **Cost overrun:** `metrics` tokens above `feature_token_budget`. **Defect:** a `defect` entry. The `phase` entry heading becomes `## <date> <time> phase <from> -> <to>`, with `(back)` when moving back. |
| 49 | R | A `defect` entry on a done feature never blocks its commit. `pd-lint` warns, and `pd-status` and the session-start summary show "retro owed" until `retro.md` exists. |
| 50 | R | A single-file item carries its own `## Now` and `## Log` sections, with the same entry shapes. |
| 51 | R | The scripts default to `docs/dev_artifacts`. When `docs/features/` exists and `.claude/pd.local.md` doesn't, `pd-status` and the session-start summary say "run /pd:adopt". All four projects adopt (§16 step 5). |
| 52 | R | A roadmap item is keyed by its slug, the id without the date, unique within the roadmap. `planned: <slug>` becomes `feature: features/<date>-<slug>` with the same slug. `after:` names slugs, and the comparison with HEAD matches by slug. |
| 53 | R | **For features**, `/pd:adopt` writes:<br>`id`: the directory name.<br>`type`: from the directory.<br>`title`: the first heading, or `.meta.json`.<br>`phase`: from `.meta.json`, or the export's last phase event.<br>`mode`: `standard` unless the export says express.<br>`branch`: from `.meta.json`, if not done.<br>`origin`: from the parent link.<br>**Legacy single-file items** get only `id`, `type`, `title` and `status`. |
| 54 | R | `plugins/pd/references/log-entries.md` holds one block per kind. A closing entry names a blocker as `review@<date> <time>#<issue id>`. |
| 55 | R | `pd-lint` resolves `backlog#<id>` in `backlog.md` or `backlog-archive.md`. |
| 56 | R | A dropped item counts as done for `after:`. `pd-status` flags its dependents for a replan. |
| 57 | R | **A legacy item that's `done`** is exempt from the phase-artifact, `metrics`, retro and `from_shape:` checks, but still checked for frontmatter vocabulary, ids and links. **A legacy item that isn't `done`** is listed by `/pd:adopt` and converted to the new artifact set before work on it resumes. |
| 58 | R | The checks use per-language regexes for import lines and path strings, for the languages a project declares. "Private" is mechanical only for Python's leading underscore; elsewhere it's the code reviewer's job. |
| 59 | R | Covered: markdown links `[..](relative path)`, and backticked relative paths that start with a moved directory, in git-tracked `.md` files. Not covered: code, absolute URLs and anything outside git. |
| 60 | R0 | So a session on any machine or worktree can resume, and changes can be reviewed in a diff. The record (§1) shows state living in one machine's database, and lost without it. |
| 61 | R0 | It means a supervisor that runs agents across many context windows and keeps progress between them. `/goal` keeps one session going, and workflows fan out within a session; neither carries progress across sessions. |
| 62 | R | Feature list = roadmaps and the backlog; progress file = `## Now` and `log.md`; git = git. Reword "nothing more" to "that recipe's file layer, plus the scripts that keep it honest". |
| 63 | R0 | It would need assignment, notifications, cross-repository views and a UI. Part B has files and a linter. |
| 64 | R | The plan is the home of mechanisms; the essay is the home of principles. The essay is committed alongside this plan (§16 step 5). Cite essay sections by number and title. |
| 65 | R | Add the commands to §A8.1: `wc -l` over the named paths, and `git log --oneline 97b3470a --since=2026-07-01 -- <paths>`. |
| 66 | D | No conflict. Recall moves to claude-mem; the cross-project views have no replacement. Both statements hold. |
| 67 | R | The diagram's source is §A2–§A5. It is redrawn by hand after edits; nothing checks drift, which is an accepted risk. Say so. |
| 68 | R | The PNG is generated and not committed; the `.mmd` is the source. The decks' images are human-doc assets; they're out of this plan's scope, and that is stated. |
| 69 | R | Add risk tags to Triage's "Hands down". |
| 70 | R | Yes. Replace "deep feature" with "standard-depth feature". |
| 71 | R | Drop "phases skipped" from `metrics`; it's derived from Triage's `phase` entries. |
| 72 | R | Each surviving cause. Fix row 1. |
| 73 | R | Yes. Calvin's input includes the PRD or RCA report the criteria derive from. |
| 74 | R | "Is this the right problem, and what would success look like?" The conductor asks them at the start of Criteria. Say so in row 1. |
| 75 | R | In scope and out of scope. Reword. |
| 76 | R | Reviewers are the design, test-case, code and security reviewers, plus calvin, whose only write is its ledger (#25). QA isn't a reviewer for this rule. |
| 77 | R | It names "none". |
| 78 | R0 | The user's later rulings settle the reading. "plan write test cases semantically, not code. Could be pseudo code." and "Design is docs, the scaffolds is at the semantic and contract level". The user then adopted "Stub-only commit 1", which has the executor write the stubs and the test code. |
| 79 | R | Nothing checks it; it's a reading aid. A commit mixing unrelated steps is a code-review note, never a blocker. Say so. |
| 80 | R | The 2026-10-13 milestone maps to Verify: one review and one QA per feature. Reword the "Independent check" cell for Execute. |
| 81 | R | It goes in the `qa` entry. A gap it names that affects a criterion is a blocker finding; otherwise it's a note. |
| 82 | R | Rename stage 7 to "Finish" everywhere. |
| 83 | D | This plan predates the method it describes. Its review rounds were the user's choice each time. |
| 84 | R | Add to D10: "(amended by D14: before code, up to three scoped review-revise cycles)". |
| 85 | R | List every stop that asks the user: a merge conflict; a cap reached (with its `capped` entry); a judgement finding with no testable check; the token cap; the stuck path; a criterion nobody can state as an observable outcome. |
| 86 | R | **Glossary:** Dn = §15 decisions; Fn and Kn = findings in the Fable reviews; #074 = a pd backlog item; Phase R = the abandoned registry re-key (§A8.1); "the existing integration script" = `followups-phase-integration-generic.js`. <br>**Provenance:** before this plan is committed, the four Fable reviews, the calvin ledger, this adjudication and the two workflow scripts are copied into a committed annex, `docs/plans/2026-10-14-thin-pd/` (it moves with the plan at adopt). |
| 87 | R | The implement result reports cycles per task (#28), and the conductor writes them in the `run` entry. |
| 88 | R | Definition in #18. In practice: the QA re-run sees no new test going red and then green, so the fix needs one. |
| 89 | R | L150 binds Execute's tasks only. In Verify, the fixer commits new tests first, and may change an existing test only when a finding says that test is wrong. |
| 90 | R | Expected results: red at the first commit; green at HEAD, after merges and in the QA battery. |
| 91 | R | The fixer proposes a rejection with file:line evidence; the conductor records it and puts it to the user. |
| 92 | R | A `decision` entry's answer line reads either "A (user, verbatim)" or "A (conductor)", and "on the user's behalf" in print mode (#42). |
| 93 | R | Open until a later `review` or `qa` entry cites it as confirmed, or the user rules. `pd-status` lists open assumptions; they don't block. |
| 94 | R | Yes. The escalated cycle reuses the implementer definition with its model overridden, and keeps the paragraph. The extra checking costs one cycle, which is accepted. |
| 95 | R | Known means the codebase already holds the same change shape. The mini-spec cites that example's path. |
| 96 | R | In Triage's `phase` entry. |
| 97 | R | Add one field list to §12. |
| 98 | R | The feature keeps small's single review call; the overrun is recorded, and nothing else changes. |
| 99 | R | More than `many_files` in `.claude/pd.local.md`, default 10. |
| 100 | R | Not a conflict. L87 sends work whose criteria look hard to state to standard depth; L177 stops if Criteria still can't state one. Reword L87 to "look hard to state". |
| 101 | R | Only after a scoped test-case review re-checks the plan, or the user does. A `review` or `decision` entry records it. |
| 102 | R | A `PreToolUse` hook on `Write` and `Edit` allows a QA agent (the hook input's `agent_type`) to write only under `agent_sandbox/`. |
| 103 | R | The files under `test_paths` that the first commit added or changed. |
| 104 | R | Update L343 to say sequential agents (D15). |
| 105 | R | No. Design and test-case reviewers receive `shape.md` and `plan.md`, read access to the code, and any prior findings; there's no diff yet. |
| 106 | R | Narrow it to "every model pd pins has a 1M-token window". Bake-off item 3 confirms it for a subagent. |
| 107 | R | The `opus` alias in agent frontmatter, which follows the latest Opus. Changing it to another model is a one-line frontmatter edit. |
| 108 | R | The user's CLAUDE.md is the home. Drop the model name here and point at it. |
| 109 | R | The implement workflow passes `model:` to `agent()` for cycles 2 and 3, overriding frontmatter. State the exception. |
| 110 | R | Executors run at `effort: medium`, set in frontmatter, and keep the verification paragraph. |
| 111 | R | Workflow names would collide with commands (`/pd:implement` exists). Rename the workflows `research-fanout`, `rca-fanout`, `implement-tasks` and `verify-change`. Commands remain the user's entry points: the stage skills start the workflows, and users don't type them. Sweep §A4, §8, §12 and the canonical diagram. |
| 112 | R | The lenses are the `brainstorming` skill's existing advisors. The conductor decides a question spans many sources, and records why in the `run` entry. |
| 113 | R | They're session files and will vanish. They're copied into the provenance annex (#86) now. |
| 114 | R | AskUserQuestion takes up to four questions per call, so rejections go in batches of four, blockers first. |
| 115 | R | The test run's console output. `pd-proof` reads only the JUnit XML. |
| 116 | R | `pd-proof` lists the greens itself in its JSON result; the merger passes the list on. Fix L805's wording. |
| 117 | R | Drop the quotation marks; it's a paraphrase of §A2. |
| 118 | R | The user's CLAUDE.md definition: the agent errors, the CLI is unavailable, it times out, or it returns no usable review. One retry at most. |
| 119 | R | The conductor drops any new finding whose file:line isn't inside a diff hunk, mechanically, from the schema. |
| 120 | R | They're recorded as notes in the `review` entry. Nobody must act on them; the retro may read them. |
| 121 | R | Qualify every use as "workflow run", "goal run" or "print-mode run". |
| 122 | R | Yes. The gate blocks while `pd-lint` fails on the feature's files. |
| 123 | R | The `run in flight:` line carries the session id. The fallback ignores a line from another session. |
| 124 | R0 | The gate's exit 2 itself continues the conversation. Turns usually call tools, which resets the 8-block count. |
| 125 | R | Reword: "it stops repeating the same block; instead it blocks once more, with the instruction to ask". |
| 126 | R | They're inferred, not measured; the bake-off's spend comparison tests them. Say so. |
| 127 | R | It returns the completed tasks, `stopped: budget` and the unstarted tasks. The conductor writes a `run` entry and asks the user: continue with a raised cap, or stop. |
| 128 | R | In the project's `.claude/settings.json` `env` block, proposed by `/pd:init`. Depth is 1; the concurrency variables keep their defaults unless the user sets them. |
| 129 | R | Principle 5 covers artifact and state rules. Delegation is a stated exception, with no mechanism (#7). |
| 130 | R | It stands for the work processed fresh in each call. Cache reads re-read the same context and would swamp it. Say so. |
| 131 | R | Reword: "Hooks hold the mechanical checks and the session-start summary". |
| 132 | R | Sweep L231 and L722: args are re-derived from `plan.md`, and the scratch args file is a convenience. |
| 133 | R | Reword: `pd-lint` takes over the doctor's role (a health check at every commit), but none of its database checks. |
| 134 | R | It covers agent-written plans. A hand-written plan isn't covered. Where the global file is absent, nothing replaces the plan-mode hook, which is an accepted risk. |
| 135 | R | They retire (L406). Remove "data-file" from L249. |
| 136 | R | The user sets them at launch, as `/pd:init`'s output explains. Without them pd loses only step-level progress; `## Now` covers resume. |
| 137 | R | A done feature of similar task count and mode. It passes within 2×, as the success test does (#203). |
| 138 | R | Add a line: §1, §2, §3 and §14 are structural; §6 and §8 rest on cost and are compensating; §15 is about the method itself. |
| 139 | R | A prevented defect leaves no record, so the figure can't show prevention. Add the caveat. |
| 140 | R | Reword to "most of the commits"; commit count is a proxy for effort. |
| 141 | R | A third of the lines written: plan documents against the change. It's context for S1, which was rejected. Reword. |
| 142 | R0 | The record can't separate the causes. The claim is only that resume is what the hand-kept files lacked. |
| 143 | R | Reword: "Retro output in the knowledge bank goes unread; the part that reached CLAUDE.md is read." |
| 144 | R | Add to §A1. pd makes the method mechanical across four projects: committed state any session can resume, gates that caught every defect in the record, and one vocabulary. Without it, the user keeps handover documents by hand, as Phase R did. |
| 145 | R | Fix the row: 1M context relaxes splitting reviews to fit a window, since reviewers read the whole artifact set and diff in one pass. S1's mention goes. |
| 146 | R | Retitle S2: "Independent reviews only at fixed moments (three; four since D14)". |
| 147 | R | Label it: "on our reading". |
| 148 | R | Partly. The hash catches a design that changed; the test-case review catches a plan that never matched it. Say so. |
| 149 | R | The CLAUDE.md of the project where the feature ran. A lesson about pd itself goes into pd's skill. |
| 150 | R | Label it: "a direction, not a measure for pd"; the bake-off measures. |
| 151 | R | Covered by #86: the provenance annex is committed. |
| 152 | R | Soften to "may be one long run; untested for Claude 5". |
| 153 | R | **Expected:** the new scripts at roughly 1–2k lines. **A guard in §16:** the build records lines added, and past 5k lines it stops for a review with the user. |
| 154 | R | They weren't mapped. A §16 build step maps each of the 43 guards to `phase-gate.sh`, `pd-lint`, or "dropped". |
| 155 | R | In `plugins/pd/scripts/`. Skills and hooks call them through `${CLAUDE_PLUGIN_ROOT}/scripts/`. |
| 156 | R | Reword to "Replaced in this design by…". |
| 157 | R | Not measured. Soften the claim; the bake-off and `metrics` will show misroutes. |
| 158 | R | By the user, at the S6 prune, using session-history usage counts. |
| 159 | R | The other workspaces stay in the read-only archive (D5). Only the four active projects adopt. Say so at L431 and L970. |
| 160 | R | Export the backlog first (step 5 runs before step 0 for pedantic-drip); step 0 moves only tracked files. Reorder. |
| 161 | R | Qualify it: every fact needed to resume lives in git. The task list, scratch args, gate state and `init-declined` are conveniences that can be lost. |
| 162 | R | One, the file itself (#50). Fix L444. |
| 163 | R | Drop the "hourly" Linear quote; keep GitHub's sub-issue progress. |
| 164 | R | By the topic name matching an item's slug; anything else is listed for the user. |
| 165 | R | Rename the human-doc sense "publishing to the human docs". |
| 166 | R | Standalone except for mermaid diagrams, which need the network; offline they show as code. Say so. |
| 167 | R | In `docs/`, beside its topic, committed, linking `doc.css` by relative path. |
| 168 | R | Add `draft`. |
| 169 | R | pd requires uv already (its Python rule), and `/pd:init` checks for it. |
| 170 | R | The local clock of the machine running `pd-new`. |
| 171 | R | It drops stopwords and keeps the first five remaining words. |
| 172 | R | `pd-new feature --from <plan> "<title>"`: the slug comes from the `planned:` line, and the title is given. |
| 173 | R | `pd-new` can't see a collision on another branch; `pd-lint` catches the duplicate at merge. |
| 174 | R | The item's first commit in `git log`. |
| 175 | R | Features and plans only. |
| 176 | R | The reason is one fact, one place, not secrecy: an issue would hold a second copy. Reword L584. |
| 177 | R | No. Inside a goal run, `pd-new` records `issue: pending`, and the next command the user invokes creates the issue. |
| 178 | R | Yes, the scan skips fenced code blocks. |
| 179 | R | `branch:` is removed at done, and is always `feature/<id>`. |
| 180 | R | One AskUserQuestion call that reaches the user. |
| 181 | R | Entry headings carry the time: `## <date> <HH:MM> <kind>`. Wall-clock is in hours. |
| 182 | R | `pd-new backlog` makes `YYYY-MM-DD-slug`; exported rows get their created date plus a slug. |
| 183 | R | `pd-lint` warns past 300 lines; the conductor runs `--archive`. |
| 184 | R | Only if the feature is `abandoned`; `pd-lint` checks. |
| 185 | R | Label it "by analogy"; the lint is the real guard. |
| 186 | R | `research-fanout` and `rca-fanout` take the question and the brainstorm or rca file. `verify-change` takes the branch, `shape.md` and `plan.md`. Only `implement-tasks` derives from `plan.md` tasks. |
| 187 | R | Yes for `git commit` run through Bash, including subagents' (hooks fire for subagent tool calls, VERIFIED in the fourth review). Commits made inside scripts aren't seen. Say so. |
| 188 | R | The summary runs on every matcher (`startup`, `resume`, `clear`, `compact`); only the `/pd:init` prompt is limited. |
| 189 | R | `plugins/pd/references/risk-patterns.md`, starting with: route decorators, migration directories, and identifiers matching auth, permission, token or secret. |
| 190 | R | `.claude/pd.local.md` carries `sop: 1`, written by `/pd:init` or `/pd:adopt`. |
| 191 | R | Cite the worktrees doc ("stays on disk until the periodic sweep"). Resume relies on branches, not worktrees (#30), so a swept worktree loses nothing. |
| 192 | R | `/pd:adopt` writes converted entries as closed (`closed: legacy`). |
| 193 | R | At the first commit, skipped tests are listed with the greens. At HEAD, a test newly skipped since the first commit fails the check. |
| 194 | R | The main session's checkout. The conductor checks out the feature branch before launching `implement-tasks`. |
| 195 | R | Keyed by the repository's `origin` URL when it has one, otherwise its path. |
| 196 | R | `/pd:adopt` runs on a `pd-adopt` branch, merged to the base branch after the user's review. Open branches are listed for their owners; Phase R's branches stay as they are. |
| 197 | R | It's for the retro and `--compare` over past features; without it, legacy features drop out. Add a clause. |
| 198 | R | Add: "D4: number unused". |
| 199 | R0 | "Retire all" retired the machinery. The three kept pieces were in §A9's finding, which the user ruled on. |
| 200 | R (user) | Committed in every project (D16). Say so in §12; `/pd:init` writes it, and it's reviewed like any config. |
| 201 | R | None. pd is disabled, and only `/pd:adopt` reads the registry, through the read-only export. The early cut is safe; say so. |
| 202 | R | Standard mode. Express, `rca-fanout` and `research-fanout` are proven by their first real use, each logged. |
| 203 | R (user) | Thin pd works if every §A7 item passes in the bake-off, and then the next five real features run with `pd-lint` clean, no registry, and median tokens within 2× of comparable past features. It fails if a §A7 item can't be fixed, or tokens run past 2× (D16). |
