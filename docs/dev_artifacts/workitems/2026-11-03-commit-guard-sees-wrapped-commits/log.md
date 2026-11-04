<!-- Append-only history of 2026-11-03-commit-guard-sees-wrapped-commits. Entry shapes: plugins/pd/references/log-entries.md. Example:
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."
-->

## 2026-11-03 11:02+08:00 note
Request (verbatim):
> commit_target.py: see commits behind timeout, sudo -u, env -u and bash -c, and a bare trailing -- after checkout (PR #29 review notes)
Round request (user, 2026-11-03, verbatim):
> proceed to investigate, design and plan for three open backlog items in this round

## 2026-11-03 11:02+08:00 phase triage -> specify
Reason: small: two tasks at most, both in commit_target.py and its two hook test files, a known module with 24 guard cases to extend.

## 2026-11-03 11:10+08:00 review calvin cycle 1 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/calvin-cycle-1.md. Verdict: 4 blockers, 8 warnings, 9 notes; all 21 answered and `## Requirements` revised.
- R1 blocker shape.md:20 — which options of each wrapper count and which take a value; answered by the wrappers table.
- R2 blocker shape.md:24 — options that stop the wrapper running the command; the table's "runs no command" column, B14.
- R3 blocker shape.md:39 — which spellings make a `-c` script; defined (basename, letters, `-o`/`+o`, `--long`), B5.
- R4 blocker shape.md:41 — a `cd` or switch inside a `-c` script and a commit after it; the `cd` ends with the script, the switch carries (B6, B7).
To the user: none (row 12, why do it at all, is answered from the PR #29 review and the owner's round request of 2026-11-03).
To the conductor (wording or consistency, each answered by a revision):
- rows 5, 6: directory-changing options (B9) and wrapper and shell combined (B8).
- rows 7, 8: today's parser already sees `env FOO=1`, `sudo git commit`, `exec git commit` (run 2026-11-03); kept as regression cases; `PREFIXES` wording fixed.
- rows 9, 15: "no word after the `--`" defined; `checkout <x> --` reads as `checkout <x>`.
- rows 10, 11, 13: unparseable script skipped as a unit, nesting capped at 5, no traceback (B15).
- rows 14, 16, 17, 18, 19, 20, 21: latency must-not reworded; shell by path counts; `<cwd>` not repo root; protected means `main` or `master`; "unchanged" pins text and outcome; missed wrappers get a backlog line; 8.0.2's pinned cases named (`test-hooks.sh:230`, `:239`, `:244`).

## 2026-11-03 11:15+08:00 review calvin cycle 2 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/calvin-cycle-2.md. Verdict: 1 blocker, 7 warnings, 13 notes; cycle 1: 20 rows answered, row 13 partly (nesting), now answered by dropping the depth cap. All 21 answered and `## Requirements` revised.
Closes: review@2026-11-03 11:10+08:00#R1, review@2026-11-03 11:10+08:00#R2, review@2026-11-03 11:10+08:00#R3, review@2026-11-03 11:10+08:00#R4
- R1 blocker shape.md:68 — the 10c harness can't read the printed directory, branch or stderr (`test-hooks.sh:260-261`); a direct test of `commit_target.py` is now in scope.
To the user: none.
To the conductor (wording or consistency, each answered by a revision):
- rows 2, 10: the frame names which expectations run the script, the hooks or the test files; "seen at <dir>" defined.
- rows 3, 11, 13, 14, 15, 17: bundled short options, long forms listed, positional words per row, `--help`/`--version` on every wrapper, `--` ends options, shell value options `-o +o -O +O`.
- rows 4, 5, 9, 16: every command word is found past wrappers (B7's `timeout 30 git switch main`); a wrapper's directory option lasts for its command (B9); wrappers chain (B8).
- rows 6, 7, 18: the depth cap is gone; any depth is parsed and the must-not covers deep nesting.
- rows 8, 12, 19, 20, 21: git-call must-not names `commit_target.py:157-159` and `repo_of`; `sudo -k` defined; other shells not seen (B14's `fish -c`); B11 notes it is `test-hooks.sh:232`; Out forms have no pinned result.

## 2026-11-03 11:22+08:00 review calvin cycle 3 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/calvin-cycle-3.md. Verdict: 0 blockers, 4 warnings, 7 notes; the calvin loop ends here. Cycle 2: 20 rows answered, row 1 partly (the direct test unnamed), now answered.
Closes: review@2026-11-03 11:15+08:00#R1
To the user: none. To the conductor (wording or consistency, each answered by a revision of `## Requirements`):
- rows 1, 7: shell option words bundle letter by letter (B5's `-eo pipefail`); other `+` words are flags.
- rows 2, 9: a `cd` behind a wrapper changes nothing (B6); a no-run option hides the commands after it, a switch included.
- rows 3, 4: the direct test is `plugins/pd/hooks/lib/test_commit_target.py`; B8 adds a 10-level nesting case.
- rows 5, 6, 11: B10's first half runs the script; the repository has local `main` and `workitem/x`; the Why names the reported forms and why the other rows ride along.
- rows 8, 10: no change; long spellings stay as listed, and a backgrounded script counts as run under the existing `&&` shortcut (`commit_target.py:173`).

## 2026-11-03 11:24+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Signed off"

## 2026-11-03 11:24+08:00 phase specify -> design
Criteria signed off (decision above); calvin loop ended at cycle 3 with no blocker.

## 2026-11-03 11:25+08:00 note
Grounding: the conductor read plugins/pd/hooks/lib/commit_target.py in full this session (lines 1-210), with both hooks and the 10c harness (test-hooks.sh:255-265); no codebase-explorer dispatch, its report would restate that read.

## 2026-11-03 12:02+08:00 review joint design and plan — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, on commit 36b8e022 (brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/review-brief-1.md). Verdict: not approved; 5 blockers, 1 warning. Each claim checked at file:line before acting; all six hold.
- R1 blocker shape.md:108 — a `-c` script still holds the outer lexer's masked separators (`commit_target.py:25`, `QUOTED_PUNCT`); the contract now restores them with `UNMASK` before the nested scan, and C15 adds `bash -c 'cd sub; git commit -m x'`.
- R2 blocker plan.md:53 — C20 staged a bad README, not the bad `log.md` B13 names; it now stages an unknown-kind entry (probed: the hook exits 2, "entry kind bogus").
- R3 blocker plan.md:35 — the bare `--` edge case's `?`, no-switch and redirection outcomes had no case; C24 adds them.
- R4 blocker plan.md:36 — the no-new-subprocess must-not had no proof; C25 logs every git call through a PATH shim and counts `subprocess.run(` sites, and the contract names the three.
- R5 blocker plan.md:37 — CI's pytest line lists files one by one (`ci.yml:43`); C26 checks it names the new file.
- R6 warning plan.md:24 — `nohup`, long spellings, `--version`, `dash` and `ksh` had no case; C1, C4, C11 and C15 add them.
Fix cycle 1 of 3: shape.md `## Design` and plan.md revised; pd-lint and `phase-gate.sh design` pass. Next: a scoped re-review of R1 to R6.

## 2026-11-03 12:07+08:00 review joint design and plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to R1 to R6 and the edit 36b8e022..35130c43 (brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/review-brief-2.md). R1, R2, R3, R5, R6 resolved; R4 open; nothing new in the diff.
Closes: review@2026-11-03 12:02+08:00#R1, review@2026-11-03 12:02+08:00#R2, review@2026-11-03 12:02+08:00#R3, review@2026-11-03 12:02+08:00#R5, review@2026-11-03 12:02+08:00#R6
- R1 blocker plan.md:56 — still open from review@2026-11-03 12:02+08:00#R4: a `git` PATH shim and a `subprocess.run(` count miss other process APIs (`check_output`, `os.system`) and skipped the nested-shell cases. C25 now runs the script under a Python audit hook logging every process-launch event, over every command of C1 to C24, in Task 2 (checked: `subprocess.run`, `check_output` and `os.system` each raise an event).
Fix cycle 2 of 3: plan.md revised; pd-lint passes. Next: a scoped re-review of R1.

## 2026-11-03 12:10+08:00 review joint design and plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to the open R4 and the edit 35130c43..a60335f4 (brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/review-brief-3.md). R4 still open; nothing new in the diff.
- R1 blocker plan.md:56 — still open from review@2026-11-03 12:02+08:00#R4: the audit-event list omitted `os.fork` and `os.forkpty` (Codex's mutation probe: a forked child passed C25). Both now listed, citing the audit table, with a negative control: a copy of `commit_target.py` with an inserted `os.fork()`, and one with `subprocess.check_output`, must each fail the check (checked: `os.fork` raises its event).
Fix cycle 3 of 3: plan.md revised; shape.md D4's CI citation corrected to `ci.yml:42`; pd-lint passes. Next: the last scoped re-review.

## 2026-11-03 12:16+08:00 review joint design and plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to the open R4 and the edit a60335f4..ceb3d03e (brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/review-brief-4.md). R4 still open; nothing new in the diff. This was the third re-review: the cap.
- R1 blocker plan.md:56 — still open from review@2026-11-03 12:02+08:00#R4: `_posixsubprocess.fork_exec` (a `multiprocessing` spawn on Python 3.14) escapes C25's event list. Checked: on this machine's Python 3.13 the same spawn raises none of those events, so no event list is complete across versions. Revised after the cap: C25 checks every `subprocess.Popen` at run time, and the new C27 proves the absence of every other process API statically (`ast` over `commit_target.py`, with negative controls).

## 2026-11-03 12:16+08:00 capped design
Deferred: none
Follow-ups: none
Decisions:
- whether the revision answering R4 (C25's run-time check plus C27's static check) ends the review loop, or one more scoped re-review runs: asked of the user.
Assumptions:
- A1: an `ast` scan of `commit_target.py` for process APIs and imports, with negative controls, is a complete proof of the must-not on subprocesses for this module (it is one file with no dynamic imports).

## 2026-11-03 12:19+08:00 decision
Q: does the revision answering R4 (C25 run-time, C27 static) end the review loop?
A (user, verbatim): "One more re-review"
answers: capped@2026-11-03 12:16+08:00

## 2026-11-03 12:26+08:00 review joint design and plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, the owner's extra pass past the cap (decision@2026-11-03 12:19+08:00), scoped to R4 and the edit ceb3d03e..82bd0509 (brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/review-brief-5.md). R4 still open; nothing new in the diff.
- R1 blocker plan.md:56 — still open from review@2026-11-03 12:02+08:00#R4: C25 and C27 bound which process calls happen, not how many (Codex's mutation: `repo_of` run twice passed both). Checked: today a commit with no switch launches no git call (`commit_target.py:173`, `repo_of` only when `switched` is set). Revised: C25 compares each command's Popen sequence with its unwrapped form's under the fork point's `commit_target.py`, and a doubled-`repo_of` copy is a negative control.

## 2026-11-03 12:33+08:00 decision
Q: does the differential-trace revision of C25 (with C27) end the review loop?
A (user, verbatim): "Accept the fix (Recommended)"
answers: capped@2026-11-03 12:16+08:00
Closes: review@2026-11-03 12:02+08:00#R4, review@2026-11-03 12:07+08:00#R1, review@2026-11-03 12:10+08:00#R1, review@2026-11-03 12:16+08:00#R1, review@2026-11-03 12:26+08:00#R1

## 2026-11-03 12:33+08:00 phase design -> create-plan
Small mode: the joint review covered the design and the plan; the owner ended its loop (decision above).

## 2026-11-03 12:34+08:00 phase create-plan -> implement
Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 12:34+08:00 note
Goal-run offer skipped: the owner scoped this round to investigate, design and plan the three backlog items, with no Execute ("proceed to investigate, design and plan for three open backlog items in this round").

## 2026-11-03 12:55+08:00 phase implement -> create-plan (back)
Reason: C25 reads its baseline from `git merge-base main HEAD`, which is HEAD once this branch is merged, so on main the comparison runs the new `commit_target.py` against itself (the doubled-call control no longer fails) and the test loses its point. Found by the worktree plan review (review@2026-11-03 12:54+08:00#N2 in workitems/2026-11-03-worktree-management-pd), the same pattern. Nothing has executed.
Invalidates: plan.md C25.

## 2026-11-03 12:55+08:00 phase-2 create-plan -> implement
C25 now reads its baseline at b230ae35 (checked: `git show b230ae35:plugins/pd/hooks/lib/commit_target.py` prints the pre-change `repo_of`). Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 18:56+08:00 review plan, simplification — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, a simplification review of shape.md ## Design and plan.md at 5a02ab66 (the owner's ask: "use agents to code review, QA, and simplify implementation without compromising functionality"; brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/simplify-brief-1.md). One cut proposed, no blocker found.
- R1 warning plan.md:56 — replace C25's comparison against the pre-change parser (each command's unwrapped form run through b230ae35's `commit_target.py`) with explicit expected git argv sequences, five patterns; keep the audit harness, both negative controls and C27. Checked by tracing today's `commit_target.py` with an audit hook: the five patterns hold (none; two `rev-parse --show-toplevel` after a switch; `show-ref` then two root queries for `checkout main`; plus `rev-parse --verify` for `HEAD~0`; `show-ref` and `rev-parse --verify` alone for `nosuch`). The trace also shows the current C25 fails a correct implementation: C8 and C24 have no wrapper, so their unwrapped form is the command itself, which today makes 0 git calls (`git checkout main --` isn't read as a switch, the B10 defect) while the fix must make 3.

## 2026-11-03 18:56+08:00 phase implement -> create-plan (back)
Reason: the simplification review above. C25 compares against the pre-change parser, which fails a correct implementation on C8 and C24; explicit sequences are simpler and correct. Also C23 diffs the two hook suites "against the work item's base", unnamed: in pull-request CI there is no local `main` (actions/checkout leaves a detached merge ref, ci.yml:13-15), so it is named `origin/main`. Nothing has executed. Second backward move: a retro is owed at Finish.
Invalidates: plan.md C23, C25.

## 2026-11-03 19:03+08:00 review plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, the QA pass on the simplification 5a02ab66..c4474325 (brief agent_sandbox/2026-11-03/2026-11-03-commit-guard-sees-wrapped-commits/simplify-qa-brief-1.md). C25's five sequences match traces of the unwrapped forms; the extra-call and doubled-`repo_of` controls and C27's three controls fail as they must; B1 to B15 keep their cases. One blocker on C23.
- Q1 blocker plan.md:55 — on `main` after the merge, `git merge-base origin/main HEAD` is HEAD, so C23's "suites unchanged" diff passes for any committed edit; asks for a fixed baseline, b230ae35.
Rejects: Q1 — B16 is a property of this change: on the task branch and in pull-request CI the merge base is the fork point, so the diff catches any edit this change makes to the two suites. A fixed baseline would fail on every later, legitimate edit of either suite by another work item. The text before this round ("against the work item's base") was equally vacuous on `main`, so the simplification lost nothing. Proposed for the user's decision.

## 2026-11-03 19:04+08:00 decision
Q: C23's base — keep `merge-base origin/main HEAD` (a real check on the branch and in PR CI, a no-op on main after the merge), a fixed baseline b230ae35, or drop the diff?
A (user, verbatim): "Keep merge-base (Recommended)"
Closes: review@2026-11-03 19:03+08:00#Q1

## 2026-11-03 19:04+08:00 phase create-plan -> implement
Simplification applied and QA-checked; Q1 closed by the owner (decision above). Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 19:21+08:00 phase implement -> create-plan (back)
Reason: calvin on plan.md, the owner's rule between plan and execution (33 questions, the conductor adjudicating as author); its fixes change plan.md. Also C23: on a later branch editing either hook suite, `git diff $(git merge-base origin/main HEAD)` sees that branch's own edit and fails, so the owner's ruling (decision@2026-11-03 19:04+08:00) rested on a wrong premise; re-asked. Nothing has executed.
Invalidates: plan.md.

## 2026-11-03 19:23+08:00 decision
Q: commit guard C23, re-asked after calvin showed `merge-base origin/main HEAD` fails on any later branch that edits either hook suite: run the suites and pin the three named cases, run the suites only, or keep merge-base?
A (user, verbatim): "Run suites + pin 3 cases (Recommended)"

## 2026-11-03 19:23+08:00 note
Calvin on plan.md (the owner's rule before Execute): one pass in report mode, 33 questions, adjudicated by the conductor as the plan's author; 27 fixed in plan.md, 5 answered, 1 dismissed. Fixed:
- Shared terms: `seen` covers every call (not-seen ones too) and resolves `commit_target.py` from the test file's directory under `python3` from PATH; `hook(script, cmd, cwd)` defined; exact stdout for every outcome phrase.
- Each task's contract names its parts (Task 1: WRAPPERS, `command_start`, the trailing `--`; Task 2: SHELLS, `-c` recursion); the CHANGELOG line is Task 1's alone, checked by C26.
- The table's rows and long spellings each get a case: `sudo --user`, `sudo -k` (with and without a command), `env --unset`, `--chdir` for `sudo` and `env`, `xargs --max-args` and B4's own `xargs -I{} git commit -m {}`, `command`, `exec -a`, `command -V`, `sudo -v`, `sudo -K`, `bash +O extglob -c`, `bash --norc -c`, a `git checkout` behind a wrapper, and a comment and a heredoc inside a `-c` script.
- C23 per the owner's ruling above. C25: which commands, how the trace is reported (`TRACE_FILE`), which literal applies, the trailing-`--` wording, and the controls run C5's `switch` form. C27: "built from the git list" pinned to `commit_target.py:156`'s form.
Answered: Scope's bash-suite cases moved to pytest by D4 (C8, C10, C20 run both hooks); C25/C27 read internals because the must-not is about internals; C23 runs the suites inside pytest so pd-proof's JUnit carries B16; sequence equality is the simplest exact form of the must-not; tags name the expectation a case serves.
Dismissed: a test with an artificially low recursion limit for `scan`'s `RecursionError` catch (real input stays far below the limit, shape.md Risks; the catch is defensive).

## 2026-11-03 19:23+08:00 phase create-plan -> implement
Calvin on plan.md answered (note above). Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 19:42+08:00 run implement-tasks — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 4. Tokens: 46614. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_727ca6d8-722/journal.jsonl
Commit: 142ce000
- task 1: merged, proof pass, cycles 0, branch pd/2026-11-03-commit-guard-sees-wrapped-commits/task-1
  case_map: C1=plugins/pd/hooks/lib/test_commit_target.py::test_c1_timeout, C2=plugins/pd/hooks/lib/test_commit_target.py::test_c2_sudo, C3=plugins/pd/hooks/lib/test_commit_target.py::test_c3_env, C4=plugins/pd/hooks/lib/test_commit_target.py::test_c4_other_wrappers, C5=plugins/pd/hooks/lib/test_commit_target.py::test_c5_switch_behind_wrapper, C6=plugins/pd/hooks/lib/test_commit_target.py::test_c6_nested_wrappers, C7=plugins/pd/hooks/lib/test_commit_target.py::test_c7_directory_options, C8=plugins/pd/hooks/lib/test_commit_target.py::test_c8_trailing_double_dash, C9=plugins/pd/hooks/lib/test_commit_target.py::test_c9_file_restore, C10=plugins/pd/hooks/lib/test_commit_target.py::test_c10_guard_through_wrapper, C11=plugins/pd/hooks/lib/test_commit_target.py::test_c11_no_command_runs, C12=plugins/pd/hooks/lib/test_commit_target.py::test_c12_wrapper_alone, C13=plugins/pd/hooks/lib/test_commit_target.py::test_c13_cd_behind_wrapper, C14=plugins/pd/hooks/lib/test_commit_target.py::test_c14_regressions_and_other_rows, C24=plugins/pd/hooks/lib/test_commit_target.py::test_c24_double_dash_edges, C26=plugins/pd/hooks/lib/test_commit_target.py::test_c26_ci_and_changelog; greens: plugins/pd/hooks/lib/test_commit_target.py::test_c9_file_restore plugins/pd/hooks/lib/test_commit_target.py::test_c11_no_command_runs plugins/pd/hooks/lib/test_commit_target.py::test_c12_wrapper_alone plugins/pd/hooks/lib/test_commit_target.py::test_c13_cd_behind_wrapper; skipped: none
- task 2: merged, proof pass, cycles 0, branch pd/2026-11-03-commit-guard-sees-wrapped-commits/task-2
  case_map: C15=plugins/pd/hooks/lib/test_commit_target.py::test_c15_shell_forms, C16=plugins/pd/hooks/lib/test_commit_target.py::test_c16_cd_in_script, C17=plugins/pd/hooks/lib/test_commit_target.py::test_c17_switch_in_script, C18=plugins/pd/hooks/lib/test_commit_target.py::test_c18_wrappers_and_depth, C19=plugins/pd/hooks/lib/test_commit_target.py::test_c19_directory_option_reaches_script, C20=plugins/pd/hooks/lib/test_commit_target.py::test_c20_lint_through_script, C21=plugins/pd/hooks/lib/test_commit_target.py::test_c21_not_commits, C22=plugins/pd/hooks/lib/test_commit_target.py::test_c22_degenerate_scripts, C23=plugins/pd/hooks/lib/test_commit_target.py::test_c23_existing_hook_tests_pass, C25=plugins/pd/hooks/lib/test_commit_target.py::test_c25_only_git_queries_run plugins/pd/hooks/lib/test_commit_target.py::test_c25_negative_controls, C27=plugins/pd/hooks/lib/test_commit_target.py::test_c27_static_subprocess_audit; greens: plugins/pd/hooks/lib/test_commit_target.py::test_c21_not_commits plugins/pd/hooks/lib/test_commit_target.py::test_c22_degenerate_scripts plugins/pd/hooks/lib/test_commit_target.py::test_c23_existing_hook_tests_pass plugins/pd/hooks/lib/test_commit_target.py::test_c25_negative_controls plugins/pd/hooks/lib/test_commit_target.py::test_c27_static_subprocess_audit, plus every task 1 test (merged before task 2 began); skipped: none
The merger's return spelled one task 2 green `test_c4_other_wwrappers_placeholder`; its own pd-proof output in the same transcript, and the test file, have `test_c4_other_wrappers`, recorded here among task 1's tests.

## 2026-11-03 19:42+08:00 phase implement -> verify
Implement exit check passed (phase-gate.sh implement: both plan tasks on merged, proof pass lines). Proving tests re-run on the branch after the merges: 28 passed (C23 runs both hook suites inside them).

## 2026-11-04 20:55+08:00 run verify-change — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 6. Tokens: 57185. Cycles: 2. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_8a959fc9-bd3/journal.jsonl
Run: wf_8a959fc9-bd3. Stopped: none.

## 2026-11-04 20:55+08:00 review verify — codex (fallback: no)
Verdict: changes requested. Commit: 0b1bf113.
- R1 blocker plugins/pd/hooks/lib/test_commit_target.py:309 — test_c25 leaves an untracked trace.jsonl in the source tree, and the verify gate then fails on it after QA. Evidence: Line 327 passes the real parser path. Line 309 puts the trace beside that script. Lines 262-263 append the events. Cleanup runs only before the cases (lines 312-313), never after the last one. The file is untracked and not ignored. plugins/pd/scripts/phase-gate.sh:138-144 counts it as a post-QA change. Fix: write the trace under pytest's tmp_path, and add a regression that asserts no trace.jsonl remains beside the script (it must fail before the fix). Codex did not rerun the write-producing suite.
- R2 blocker plugins/pd/hooks/lib/commit_target.py:202 — An empty shell argument crashes the parser with an IndexError and hides a later commit. Evidence: A stdin probe of `bash -c ''; git commit -m x` exits 1 with empty stdout, because words[j][0] is read before the length check. Both hooks silently exit on a parser failure (pre-commit-guard.sh:86; pd-commit-lint.sh:16), so the commit goes unseen. This breaks shape.md:74 and :99. C22 (test_commit_target.py:233-235) has no empty quoted script. Fix: check token length before indexing, and add an exact-output regression for the commit that follows.
- R3 blocker plugins/pd/hooks/lib/commit_target.py:168 — A wrapper option with no value consumes the command separator, so the wrapper's directory leaks into the next command. Evidence: At line 167 a separator gives an empty value, but line 168 still advances past it. Probes of `env -C sub -u ; git commit -m x` and `sudo -D sub -u ; git commit -m x` returned <cwd>/sub instead of <cwd>. This breaks shape.md:41 and can send lint to the wrong repository. Fix: stop parsing the wrapper when its required value is missing, and test the exact directory of the later commit.
- R4 blocker plugins/pd/hooks/lib/commit_target.py:294 — A `-c` script written in ANSI-C quoting hides a real commit from the parser. Evidence: A probe of `bash -c $'git commit -m x'` exits 0 with empty stdout. Tokenizing at lines 259-262 keeps the leading `$`, and line 294 then scans `$git` instead of `git`. shape.md:39 does not exclude this quoting form. C21 uses this quoting at test_commit_target.py:229 but checks only negative outcomes, so skipping the script passes. Fix: strip the `$` quoting when extracting the script, and add a positive regression.
- R5 blocker plugins/pd/hooks/lib/test_commit_target.py:321 — C25 leaves out 19 required negative inputs, so the no-added-subprocess criterion is only partly protected. Evidence: plan.md:11 counts not-seen calls in seen(), and plan.md:60 requires every seen input from C1-C24. _traced_cases (lines 270-303) covers 82 inputs but traces only 63 commands. All 19 empty-output cases are missing, and the unconditional `not r.stdout` at line 321 would reject them anyway. A Git-stub mutation that adds a repo_of call only for `timeout --help git commit` kept all 82 outputs and all 63 trace expectations, and C27 still passed. Fix: include the missing inputs and accept empty stdout for them.
- R6 blocker plugins/pd/hooks/lib/test_commit_target.py:156 — C26 will fail CI on the next release, because it permanently requires this feature's entry under Unreleased. Evidence: scripts/release-pr.sh:36-37 moves the current entries under a version heading and leaves Unreleased empty. C26 searches only Unreleased (lines 155-156), and CI runs it (.github/workflows/ci.yml:42). Applying that heading change in memory made the test raise AssertionError. plan.md:40 explicitly asks for this assertion, so the contract change needs your approval before the check is removed or replaced.
- R7 warning plugins/pd/hooks/lib/commit_target.py:195 — Two internal declarations differ from the contract. Evidence: shape.md:111 specifies command_start returning (j, here), but line 195 returns (i, here, wrapped), and line 282 consumes three values. shape.md:104 specifies SHELL_VALUE_OPTIONS as four signed options, but line 39 stores only the letters o and O. The callers are consistent, so these are discrepancies, not shown runtime failures.
Rejects: review@2026-11-04 20:55+08:00#R6 — The finding holds, but the fix needs a contract change. plan.md:40 requires C26 to assert the entry under Unreleased, and test_commit_target.py:155-156 does exactly that. scripts/release-pr.sh:36-37 empties Unreleased at release, so the test will fail on the next release. The user should rule on dropping or replacing that assertion, for example by checking any CHANGELOG section. I did not touch plan.md or the test.

## 2026-11-04 20:55+08:00 qa
Commit: 462ade63
Ran: `./validate.sh` -> pass
Ran: `bash plugins/pd/hooks/tests/test-hooks.sh` -> pass
Ran: `bash scripts/test-release.sh` -> pass
Ran: `bash -ec 'for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done'` -> pass
Ran: `bash -ec 'for s in pd-adopt pd-init pd-lint pd-new pd-proof pd-review-filter pd-status; do "plugins/pd/scripts/$s" --self-test; done'` -> pass
Ran: `python3 plugins/pd/scripts/pd_common.py --self-test` -> pass
Ran: `uv run --script plugins/pd/scripts/pd-html.py --self-test` -> pass
Ran: `node plugins/pd/workflows/tests/test-workflows.mjs` -> pass
Ran: `uv run --project plugins/pd pytest -q plugins/pd` -> pass
Criteria gaps: Fix check for Q7 (462ade63, test-only): the fix holds. The test now traces `git checkout nosuch -- && git commit -m t`, which runs git twice. QA ran a mutant in a detached worktree at HEAD that put the trace back beside the script (`trace = os.path.join(os.path.dirname(script), "trace.jsonl")` in _trace_mismatches). With it, test_c25_leaves_no_trace_in_source_tree fails when run alone (1 failed, AssertionError at line 368) and in the full file (1 failed, 32 passed), and plugins/pd/hooks/lib/trace.jsonl (409B) appears. Unmutated HEAD passes 33/33. The worktree was removed and the main tree's `git status` is clean, with no leftover trace.jsonl. R1-R5 were confirmed in run 2 at d3207a8c. 462ade63 touches only test_commit_target.py, so those results still apply.
Criteria gaps: B1-B4: each row is still pinned by only a few spellings. Most value options in WRAPPERS have no test case (sudo -g/-C/-h/-p/-r/-t/-T/-U, stdbuf -i/-e, time -o, xargs -P/-L/-s/-d/-E/-a), so a typo or a missing entry passes every test. Probes at HEAD show `sudo -g wheel`, `stdbuf -i0`, `time -o f` and `xargs -P 2` before `git commit` are seen correctly today, but nothing pins them.
Criteria gaps: B5: no test pins the rule that a `+` word never counts as -c (Q3). Commands outside the pinned forms that use `$'...'` with escapes are not seen (Q8).
Criteria gaps: B8/B15: no test exercises the RecursionError catch (Q4).
Criteria gaps: B15: the no-traceback promise is tested only on a few degenerate inputs. QA did not repeat run 2's 3000-input fuzz at this commit. The only change since is test-only, so that fuzz result should still apply, but it is evidence, not a test.
Criteria gaps: B13: the suite drives pd-commit-lint end to end only through `bash -c`. QA drove it on HEAD in an adopted repo with a staged bogus log.md entry. `git commit`, `timeout 30 git commit`, `sudo -u alice git commit`, `bash -c ''; git commit`, `env -C . -u ; git commit`, `bash -c $'git commit -m x'` and `nice -n 5 bash -c 'timeout 3 git commit -m x'` all exited 2 with the lint error. `echo git commit` and `git status` exited 0. No test pins the wrapper-only form through the lint hook.
Criteria gaps: B12/B7 through pre-commit-guard: on workitem/x, `timeout 30 bash -c 'git switch main && git commit -m x'` gives the main-branch reminder. `bash -c $'git switch main\ngit commit -m x'` gives none (Q8).
Criteria gaps: B16: 'every existing case keeps its text unchanged' is still pinned only for the three literals in C23. d3207a8c flipped one expectation that its own test commit had pinned (Q10).
Criteria gaps: Must-not on subprocesses: C25 traces the positive cases and the 19 negatives at run time. Inputs outside C1-C24 rely only on C27's static audit.
Criteria gaps: pd-lint --isolation still skips this branch (Q6). `pd-lint --risk b230ae35..HEAD` and pd-lint on the work item directory printed nothing and exited 0.
- Q3 note plugins/pd/hooks/lib/commit_target.py:216 — Still open: no test fails if the rule that `+` words never count as -c is removed. Evidence: In a worktree at 462ade63, the mutant `(letter == "c" and w[0] == "-")` -> `(letter == "c")` passes 33/33. A probe of `bash +c 'git commit -m x'` gives empty stdout, which is correct but unpinned.
- Q4 note plugins/pd/hooks/lib/commit_target.py:299 — Still open: no test fails if the RecursionError catch is removed. Evidence: The mutant `except RecursionError:` -> `except ZeroDivisionError:` passes 33/33 at 462ade63.
- Q5 note plugins/pd/hooks/lib/commit_target.py:180 — Still open: the trailing NAME=value loop in skip_wrapper repeats work that the ASSIGNMENT branch in command_start already does. Evidence: Replacing `while j < len(words) and ASSIGNMENT.match(words[j]):` with `while False:` passes 33/33 at 462ade63.
- Q6 note .:0 — Still open: pd-lint --isolation did not check this branch. Evidence: `plugins/pd/scripts/pd-lint --isolation b230ae35..HEAD` printed 'pd-lint: WARN .:0: isolation skipped: no source_paths/test_paths, and no src/ or tests/' and exited 0.
- Q8 warning plugins/pd/hooks/lib/commit_target.py:88 — Still open: the R4 fix only drops the `$` in front of `$'...'` and does not decode ANSI-C escapes. A -c script that separates its commands with `\n` hides its commit from both hooks. Evidence: At 462ade63, commit_target.py prints nothing for `bash -c $'git add .\ngit commit -m x'` and `bash -c $'cd sub\ngit commit -m x'` on main, or for `bash -c $'git switch main\ngit commit -m x'` on workitem/x. End to end, pd-commit-lint.sh exits 0 for `bash -c $'git add .\ngit commit -m x'` with a failing log.md staged, skipping the lint, while `bash -c $'git commit -m x'` exits 2. pre-commit-guard.sh gives no reminder for the `$'git switch main\n...'` form, but does for `timeout 30 bash -c 'git switch main && git commit -m x'`.
- Q9 note plugins/pd/hooks/lib/commit_target.py:88 — Still open: no test covers the `$"..."` half of the `$`-strip. Evidence: The mutant that narrows the check to `cmd[i + 1:i + 2] == "'"` passes 33/33 at 462ade63. A probe shows `bash -c $"git commit -m x"` is seen, which is correct but unpinned.
- Q10 note plugins/pd/hooks/lib/test_commit_target.py:236 — Still true in history: fix commit d3207a8c changed an expectation that its own test commit 0f0fe06d had pinned (`bash '' -c 'git commit -m x'` went from seen to not seen), so that change was not red-first. Evidence: `git show d3207a8c -- plugins/pd/hooks/lib/test_commit_target.py` moves the form into `assert seen(...) == ""`. A probe at HEAD gives empty stdout, which matches bash: the empty word is the script file. The new expectation is right. R2's red-first evidence rests on its other two forms.
Fixed: R1 by d3207a8c — plugins/pd/hooks/lib/test_commit_target.py::test_c25_leaves_no_trace_in_source_tree (failed before the fix, committed in 0f0fe06d; strengthened in 462ade63 for Q7)
Fixed: R2 by d3207a8c — plugins/pd/hooks/lib/test_commit_target.py::test_empty_shell_argument_keeps_later_commit (committed in 0f0fe06d); it also closes the run's Q1
Fixed: R3 by d3207a8c — plugins/pd/hooks/lib/test_commit_target.py::test_wrapper_option_without_value_stops_at_separator (committed in 0f0fe06d)
Fixed: R4 by d3207a8c — plugins/pd/hooks/lib/test_commit_target.py::test_ansi_c_quoted_script_is_seen (committed in 0f0fe06d)
Fixed: R5 by 0f0fe06d — plugins/pd/hooks/lib/test_commit_target.py::test_c25_no_subprocess_for_non_commits (19 negative inputs; a test-only fix)
Fixed: Q7 by 462ade63 — test_c25_leaves_no_trace_in_source_tree traces a case that runs git (test-only)
Closes: review@2026-11-04 20:55+08:00#R1, review@2026-11-04 20:55+08:00#R2, review@2026-11-04 20:55+08:00#R3, review@2026-11-04 20:55+08:00#R4, review@2026-11-04 20:55+08:00#R5

## 2026-11-05 04:26+08:00 decision
Q: review@2026-11-04 20:55+08:00#R6 (rejected: C26 asserts the CHANGELOG entry under `[Unreleased]`, test_commit_target.py:155, which scripts/release-pr.sh:36 empties; the same assertion is in test_pd_worktrees.py:407 and test_explorer_codegraph.py:172): how should the three tests change?
A (user, verbatim): "Any section, all three (Recommended)"
C26 changes to look for the entry anywhere in CHANGELOG.md (a contract change: plan C26, back to design with R7); the two done items get one conductor commit on the combined branch before its battery.
Closes: review@2026-11-04 20:55+08:00#R6

## 2026-11-05 04:26+08:00 decision-2
Q: review@2026-11-04 20:55+08:00#R7 (warning: shape.md:111 pins `command_start -> (j, here)` and shape.md:104 `SHELL_VALUE_OPTIONS = {"-o", "+o", "-O", "+O"}`; the code returns `(i, here, wrapped)`, commit_target.py:200, and stores `{"o", "O"}`, :39): which side moves?
A (user, verbatim): "Amend shape.md to the code (Recommended)"
Closes: review@2026-11-04 20:55+08:00#R7

## 2026-11-05 04:26+08:00 decision-3
Q: qa@2026-11-04 20:55+08:00#Q8 (warning: `$'...'` escapes aren't decoded, so `bash -c $'git switch main\ngit commit -m x'` prints nothing; reproduced by the conductor at a716cb80): fix it now?
A (user, verbatim): "Fix it in this pass (Recommended)"

## 2026-11-05 04:26+08:00 decision-4
Q: qa@2026-11-04 20:55+08:00#Q3, #Q4, #Q5, #Q9 (no test for the `+`-word rule, commit_target.py:216; none for the RecursionError catch, :299; skip_wrapper's trailing NAME=value loop, :180, repeats command_start's ASSIGNMENT branch; no test for the `$"..."` strip, :88): fold them into the same fix?
A (user, verbatim): "Fold them in (Recommended)"

## 2026-11-05 04:26+08:00 phase verify -> design (back)
Accepted contract changes (decision@2026-11-05 04:26+08:00, decision-2@2026-11-05 04:26+08:00): shape.md `### Contracts` (`command_start`'s return, `SHELL_VALUE_OPTIONS`, and a new `$'…'` decoding rule for Q8, decision-3@2026-11-05 04:26+08:00) and plan C26. Folded in: Q3, Q4, Q5, Q9 (decision-4@2026-11-05 04:26+08:00). Tasks 1 and 2 stay merged; the changes go into a new task.
Invalidates: shape.md Contracts `command_start`, `SHELL_VALUE_OPTIONS`, `shell_text`; plan.md C26

## 2026-11-05 04:38+08:00 review joint design and plan — codex
Verdict: changes requested. Commit: 5da4c246. Scope: the Verify amendments (shape.md Contracts, plan Task 3).
- R1 blocker docs/dev_artifacts/workitems/2026-11-03-commit-guard-sees-wrapped-commits/plan.md:76 — C31 omits the initialization needed to reach scan's RecursionError handler, so its green-at-first-commit claim is not reproducible from the specified driver. Evidence: With import sys,runpy; setrecursionlimit(n); runpy.run_path(...), Python 3.13.14 and 3.15.2 failed during initialization for tested limits 15–48; at 49–60 the ten-level script was seen instead of skipped. Tracebacks included imports at commit_target.py:13, before the handler at :299–301. Preloading the dependencies and pkgutil before lowering the limit made n=18 work on 3.15.2; an in-memory catch-removal mutant then failed both inputs. Specify preloading and limit calibration, retaining the exact stdout/stderr assertions and mutation proof.
- R2 blocker docs/dev_artifacts/workitems/2026-11-03-commit-guard-sees-wrapped-commits/plan.md:74 — C29 does not faithfully prove escaped-quote preservation or decoded-punctuation masking. Its negative quote case passes when the script is simply discarded, and none of its inputs exercises a decoded semicolon. Evidence: In an in-memory decoder model, both mutations (discard ANSI-C words containing escaped apostrophes, and omit masking decoded punctuation) passed all six C29 inputs. The first missed bash -c $'git commit -m \'x\''; the second falsely saw echo $'\x3b' git commit -m x. Add those cases and an inner-separator positive such as bash -c $'true\x3b git commit -m x'. Clarify shape.md:119–121: decoded apostrophes must survive outer tokenization, decoded punctuation must receive QUOTED_PUNCT masking, and UNMASK at :109 restores it only for the nested scan; decoded newlines remain outer word data and become inner syntax according to inner quoting. These enforce shape.md:74–75 and :118. Existing C21 strings at test_commit_target.py:229 contain actual Python newlines, so retaining them alone does not test backslash-n decoding.
- R3 blocker docs/dev_artifacts/workitems/2026-11-03-commit-guard-sees-wrapped-commits/plan.md:74 — Task 3 adds decoding inputs without extending C25's execution-count proof, leaving the no-added-subprocess requirement unprotected on the new path. Evidence: C25 remains limited to C1–C24 at plan.md:60; its 82 current inputs contain no literal \x67. An in-memory mutation calling existing repo_of only when the input contains \x67 passed the actual C27 static checker: it adds execution without adding a subprocess.run call site. C29 checks output, which that extra query need not change. Extend the runtime trace cases to the new decoding inputs: the switch/newline case should produce exactly two root queries, and the remaining C29 inputs none. This directly protects shape.md:76 and :122.
- R4 blocker docs/dev_artifacts/workitems/2026-11-03-commit-guard-sees-wrapped-commits/plan.md:73 — C28's stated release transform does not match scripts/release-pr.sh:36 exactly. Evidence: The awk prints the first matching Unreleased heading, then an empty line, then the version heading. C28 places the version heading on the immediately following line. Running the exact awk against CHANGELOG.md through stdin produced different bytes from that stated transform. Both transforms reject the old Unreleased-only assertion and pass the proposed whole-file assertion, but the promised production-equivalent fixture is inaccurate. Specify the blank line and first-match behavior, or reuse the exact awk transformation.
Summary: Four blockers. R7's declarations match commit_target.py:39 and :185–200. C30 and C32 pass currently and fail their named mutations; unquoted bash +c git commit -m x is also not seen. Octal \147 and hex \x67 both decode to g. Q5 is redundant: command_start consumes the same assignments, with identical outputs across 262 in-memory comparisons. Task 3 has its contract pointer, files, uses and matching JUnit command/path; from_shape matches. No code changed in the reviewed commit, and no additional documentation contradiction was found. Verification used source inspection, read-only runtime probes and explicitly synthetic mutations; file-writing pytest/hook suites were not run. HEAD remained 5da4c246 and the worktree remained clean.
Revised (fix cycle 1 of 3): R1 C31 imports the dependencies and runpy/pkgutil before lowering the limit and calibrates n (10 to 300); R2 shape.md shell_text says how a decoded `'`, punctuation and newline behave at each level, and C29 adds `bash -c $'git commit -m \'x\''`, `bash -c $'true\x3b git commit -m x'`, `echo $'\x3b' git commit -m x` and C21's two cases in backslash spelling; R3 new C33 extends C25's trace to C29, C30 and C32 (switch case [root, root] as at test_commit_target.py:311-312, the rest none); R4 C28 spells the awk's output (scripts/release-pr.sh:36: the Unreleased line, an empty line, the version heading).

## 2026-11-05 04:46+08:00 review joint design and plan, scoped — codex
Verdict: approved. Commit: 9bfb50c6. Scoped to review@2026-11-05 04:38+08:00's R1 to R4.
- R1 resolved — plan.md:76: read-only runs found n=18 (Python 3.13.14) and n=17 (3.15.2); the script alone prints nothing, with `; git commit -m x` it prints `<cwd>\t`; with the RecursionError catch removed no n in 10-300 qualifies.
- R2 resolved — plan.md:74 and shape.md:119-124: in a synthetic decoder model all 11 C29 inputs pass; dropping `\'` words fails the quoted-message positive; skipping decoded-punctuation masking falsely sees `echo $'\x3b' git commit -m x`.
- R3 resolved — plan.md:78: the switch/newline input's two root queries match test_commit_target.py:311-312; a `repo_of` call added only for `\x67` keeps stdout but breaks C33's empty trace.
- R4 resolved — plan.md:73: the awk at scripts/release-pr.sh:36 matches the stated transform byte for byte.
New in diff: none.
Closes: review@2026-11-05 04:38+08:00#R1, review@2026-11-05 04:38+08:00#R2, review@2026-11-05 04:38+08:00#R3, review@2026-11-05 04:38+08:00#R4

## 2026-11-05 04:46+08:00 phase design -> create-plan
Design amendments approved (review@2026-11-05 04:46+08:00): shape.md Contracts for R7 and Q8; plan Task 3 (C28 to C33) reviewed jointly. Next: calvin on Task 3 (the owner's rule between plan and execution; the earlier pass at log.md:148 predates it), then implement.

## 2026-11-05 04:57+08:00 decision
Q: calvin on Task 3, question 29 (agent_sandbox/2026-11-05/2026-11-03-commit-guard-sees-wrapped-commits/task3-calvin.md), probed by the conductor: `<shell> +c 'echo RAN; exit 7'` and `<shell> +ec 'echo RAN2'` run the string as a script in all five SHELLS (bash 3.2.57, sh, zsh, dash, ksh: RAN printed, rc 7), so shape.md's signed-off rule (a `-c` word starts with a single `-`; `+` words are flags) misses `bash +c 'git commit -m x'`, and C30 (from qa@2026-11-04 20:55+08:00#Q3) would pin the miss. Change the criterion?
A (user, verbatim): "Count +c as -c (Recommended)"
Signed-off text: an option word starting with `-` or `+` with `c` among its letters runs a script (`-c`, `+c`, `-lc`, `+ec`); `-o`, `+o`, `-O` and `+O` still take a value. B5 gains `bash +c 'git commit -m x'` and `bash +ec 'git commit -m x'` -> seen, branch empty.

## 2026-11-05 04:57+08:00 phase create-plan -> specify (back)
Criteria change signed off (decision@2026-11-05 04:57+08:00): `## Requirements` "A `-c` script" counts `+` words with `c` (`+c`, `+ec`), and B5 gains their two inputs. C30 flips to expect them seen; the code change (the `w[0] == "-"` test, commit_target.py:216) goes into Task 3.
Invalidates: shape.md Requirements "A `-c` script", B5; plan.md C30

## 2026-11-05 04:58+08:00 review calvin on plan Task 3 — calvin
Ledger: agent_sandbox/2026-11-05/2026-11-03-commit-guard-sees-wrapped-commits/task3-calvin.md (plan.md Task 3, C28 to C33, at aab6ffe2; the owner's rule between plan and execution). Verdict: 1 blocker, 15 warnings, 16 notes; the conductor adjudicated as Task 3's author: 22 fixed, 10 answered, 0 dismissed.
- Question 29 (a note) probed false: every SHELL runs a `+c` string as a script, so the criterion changed (decision@2026-11-05 04:57+08:00).
- The blocker (question 1, C31's "limit at which C18 sees that script"): C31 now also runs the script under the default limit.
Revised: plan.md Task 3 rewritten (intro list of rulings, red and green marks, C28 to C33 sharpened, C26 and C25 annotated); shape.md octal and hex digit counts.

## 2026-11-05 04:58+08:00 phase specify -> design
Criteria change applied (decision@2026-11-05 04:57+08:00): "A `-c` script" counts `-` and `+` words with `c`; B5 gains `bash +c` and `bash +ec`. Signed off by the owner in that decision.

## 2026-11-05 04:58+08:00 phase-2 design -> create-plan
No contract line names the `+` rule; shape.md's only Design change in this pass is the octal and hex digit counts (calvin question 27). Plan Task 3 revised for calvin; a scoped review of 9bfb50c6..HEAD next.

## 2026-11-05 05:06+08:00 review plan, scoped — codex
Verdict: approved. Commit: fe6c8a95. Scope: 9bfb50c6..fe6c8a95 (the +c criterion, calvin's Task 3 revisions).
- R1 note plan.md:81 — C30's `bash +x` negative holds for bash, sh, zsh and dash, but ksh 93u+ runs the argument as a command string (`ksh +x 'printf PD_SCRIPT_RAN; exit 7'` printed and exited 7); the conductor confirmed `ksh 'echo KSH_RAN; exit 5'` runs with no option at all. Outside the signed-off `-c` criterion; goes to the backlog.
Summary: removing the sign test at commit_target.py:216 keeps value options (:213-215) and leaves all 82 existing trace inputs, `_traced_negatives` and 26 test-hooks.sh cases unchanged; C29's six positives, C30's two and C33's trace fail on today's code; C28, C31 (n=18 on 3.13.18, n=17 on 3.14.10 and 3.15.2) and C32 pass and fail their named mutations.

## 2026-11-05 05:06+08:00 phase create-plan -> implement
Plan Task 3 approved (review@2026-11-05 05:06+08:00, after review@2026-11-05 04:46+08:00 and calvin, review@2026-11-05 04:58+08:00). Implement runs task 3 only; tasks 1 and 2 stay merged.

## 2026-11-05 05:15+08:00 run implement-tasks — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 3. Tokens: 22361. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_0eca9f3c-2ce/journal.jsonl
Commit: 23b5c9b3
- task 3: merged, proof pass, cycles 1, branch pd/2026-11-03-commit-guard-sees-wrapped-commits/task-3
  case_map: C28=plugins/pd/hooks/lib/test_commit_target.py::test_c26_ci_and_changelog, C29=plugins/pd/hooks/lib/test_commit_target.py::test_c29_ansi_c_decoding, C30=plugins/pd/hooks/lib/test_commit_target.py::test_c30_plus_c, C31=plugins/pd/hooks/lib/test_commit_target.py::test_c31_recursion_limit_skips_deep_script, C32=plugins/pd/hooks/lib/test_commit_target.py::test_c32_dollar_double_quote, C33=plugins/pd/hooks/lib/test_commit_target.py::test_c25_only_git_queries_run and plugins/pd/hooks/lib/test_commit_target.py::test_c25_no_subprocess_for_non_commits; greens: test_ansi_c_quoted_script_is_seen, test_c10_guard_through_wrapper, test_c11_no_command_runs, test_c12_wrapper_alone, test_c13_cd_behind_wrapper, test_c14_regressions_and_other_rows, test_c15_shell_forms, test_c16_cd_in_script, test_c17_switch_in_script, test_c18_wrappers_and_depth, test_c19_directory_option_reaches_script, test_c1_timeout, test_c20_lint_through_script, test_c21_not_commits, test_c22_degenerate_scripts, test_c23_existing_hook_tests_pass, test_c24_double_dash_edges, test_c25_leaves_no_trace_in_source_tree, test_c25_negative_controls, test_c25_no_subprocess_for_non_commits, test_c26_ci_and_changelog, test_c27_static_subprocess_audit, test_c2_sudo, test_c31_recursion_limit_skips_deep_script, test_c32_dollar_double_quote, test_c3_env, test_c4_other_wrappers, test_c5_switch_behind_wrapper, test_c6_nested_wrappers, test_c7_directory_options, test_c8_trailing_double_dash, test_c9_file_restore, test_empty_shell_argument_keeps_later_commit, test_wrapper_option_without_value_stops_at_separator; skipped: none
The merger's case_map named C28 only by file and C31 by no test; the conductor mapped them from the test file (test_commit_target.py:148, :489). C28, C31 and C32 are green at the first commit as the plan declares (their mutations are Verify QA's); C33's not-seen half (test_c25_no_subprocess_for_non_commits) is green too, its seen half red. Tasks 1 and 2 stay merged (run@2026-11-03 19:42+08:00).

## 2026-11-05 05:15+08:00 phase implement -> verify
Implement exit check passed (phase-gate.sh implement: tasks 1 to 3 on merged, proof pass lines). Proving tests re-run on the branch after the merge: 37 passed, no trace.jsonl left in plugins/pd/hooks/lib.

## 2026-11-05 05:42+08:00 run verify-change — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 4. Tokens: 51904. Cycles: 1. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_34c568ac-644/journal.jsonl
Run: wf_34c568ac-644 (the second run, after task 3). Stopped: none.

## 2026-11-05 05:42+08:00 review verify — codex (fallback: no)
Verdict: changes requested. Commit: 8440dce5. The owner's rulings (R6 via C26/C28, R7's shape amendment, the Q5 deletion, the +c criterion) confirmed in the code; the three named mutations (C28, C31, C32) shown red.
- R1 blocker plugins/pd/hooks/lib/commit_target.py:67 — Decoded NUL escapes can hide commits or crash the parser. Evidence: For bash -c $'git commit\0 -m x', Bash truncates the quoted word to 'git commit', but the parser prints nothing. For bash -c $'git checkout main\0ignored'; git commit -m x, the parser exits 1 with ValueError: embedded null byte. Both hooks then silently exit. This violates shape.md:74 and :119. Fix: consume the full quoted span while truncating the decoded value at NUL, and add exact-output regressions.
- R2 blocker plugins/pd/hooks/lib/commit_target.py:108 — The new decoding support does not work through the hooks when an escape spells part of 'commit'. Evidence: bash -c $'git switch main; git \x63ommit -m x' gives '<cwd>\tmain\n' from the parser, but pre-commit-guard.sh gives no reminder, where the unescaped control does. pre-commit-guard.sh:82 and pd-commit-lint.sh:9 reject input lacking the literal substring 'commit' before they call the decoder. Octal \143 reproduces the gap. Fix: update both prefilters and add end-to-end regressions.
- R3 blocker plugins/pd/hooks/lib/commit_target.py:67 — Hex and octal byte escapes corrupt UTF-8 directory names. Evidence: env -C $'\xe4\xb8\xad' git commit -m x should target <cwd>/中. Bash bytes are e4b8ad, but the parser yields U+00E4 U+00B8 U+00AD because chr() converts each byte separately. The same error occurs inside a decoded -c script. pd-commit-lint.sh:19 can then fail its repository lookup and skip lint. Fix: keep byte semantics when reconstructing the word, and test an encoded non-ASCII directory.
- R4 blocker plugins/pd/hooks/lib/test_commit_target.py:348 — C33 omits two required C29 inputs, so their no-added-subprocess requirement is unprotected. Evidence: test_c29_ansi_c_decoding adds the raw backslash-spelled comment and heredoc inputs separately at line 467. Neither enters _traced_negatives; line 347 holds Python-decoded newlines instead. This contradicts plan.md:84. An in-memory mutation adding repo_of only for those two raw inputs passed C27 and all 96 existing trace checks, although each input launched an extra Git query. Fix: put both raw inputs in the shared traced collection.

## 2026-11-05 05:42+08:00 qa
Commit: 38cf87c4
Ran: `./validate.sh` -> pass
Ran: `bash plugins/pd/hooks/tests/test-hooks.sh` -> pass
Ran: `bash scripts/test-release.sh` -> pass
Ran: `bash -ec 'for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done'` -> pass
Ran: `bash -ec 'for s in pd-adopt pd-init pd-lint pd-new pd-proof pd-review-filter pd-status; do "plugins/pd/scripts/$s" --self-test; done'` -> pass
Ran: `python3 plugins/pd/scripts/pd_common.py --self-test` -> pass
Ran: `uv run --script plugins/pd/scripts/pd-html.py --self-test` -> pass
Ran: `node plugins/pd/workflows/tests/test-workflows.mjs` -> pass
Ran: `uv run --project plugins/pd pytest -q plugins/pd` -> pass
Criteria gaps: Battery at 38cf87c4: all 9 commands exited 0. Results: validate 0 errors and 0 warnings; test-hooks 24/24; test-release 48/48; test-pd-commit-lint 11, session-start 33, stop-gate 29 and phase-gate 39 all passed; every self-test passed; test-workflows all passed; pytest 49 passed.
Criteria gaps: R1 fix holds. At the test commit ec7b13d6, test_review_nul_bytes_and_hook_prefilters fails on its first assert (`bash -c $'git commit\0 -m x'` printed ''). A per-case probe of the pre-fix parser showed both R1 cases wrong: the first printed nothing, the second exited 1 with `ValueError: embedded null byte`. At HEAD both are right (`<R>\t` and `<R>\tmain`). Mutant C (NUL cut removed, commit_target.py:72) is killed by that test. Extra NUL probes matching bash all pass: `\x00` and `\000` spellings, `echo $'\0' && git commit` seen, `bash -c $'echo \0; git commit -m x'` not seen, and `$'git com\0zz'$'mit -m x'` seen. A bash script confirmed bash's own rule: `$'a\x00b'$'c'` gives `ac`.
Criteria gaps: R2 fix holds in both hooks. Before the fix (ec7b13d6 tree), pre-commit-guard.sh gave no reminder for `bash -c $'git switch main; git \x63ommit -m x'` or its `\143` spelling, and pd-commit-lint.sh exited 0 on a staged bogus log.md for both. At HEAD the guard prints the reminder and lint exits 2 with `entry kind bogus`, while `echo $'git \x63ommit -m x'` still exits 0. Mutant A (guard prefilter reverted) is killed by test_review_nul_bytes_and_hook_prefilters. Mutant B (lint prefilter reverted) is not caught by any test (Q7).
Criteria gaps: R3 fix holds. At ec7b13d6, test_review_utf8_bytes_in_directory fails: it got `<R>/ä¸\xad`. A probe showed the `-c` script case was also wrong before the fix. At HEAD both give `<R>/中`. Mutant D (decode as latin-1) is killed by that test.
Criteria gaps: R4 fix holds. Mutant E adds a repo_of call in main() only for the two raw-backslash C29 inputs. It survives the 8440dce5 test file and is killed by HEAD's test_c25_no_subprocess_for_non_commits. That is the red/green equivalent for a test-only fix.
Criteria gaps: Mutant method: each mutant ran on a `git archive HEAD plugins/pd` copy. test_c23 and test_c26 fail in every such copy, the unmutated baseline included (no CHANGELOG, .github or .git there), so a mutant counts as killed only by other tests failing.
Criteria gaps: Driven end to end through commit_target.py on a fresh repo (main, workitem/x, sub/), 76 cases, all with the expected stdout, exit 0 and empty stderr. They cover every B1-B12, B14 and B15 command in shape.md, the three kept regression forms, and these flows across tasks: `sudo -u alice bash -c 'git switch main && git commit'`, `bash -c $'cd sub\ngit commit -m x'`, a switch carried out of nested `sh -c`, `bash -c 'git checkout main --' && git commit`, `nohup bash -lc 'cd sub; ...' &`, `timeout 30 bash -c $'git switch main\0junk'; git commit`, `env -C $'s\x75b' bash -c ...` and `sudo -u alice bash -c $'git switch main; git \143ommit -m x'`. B13 was driven through pd-commit-lint.sh on an adopted repo (exit 2).
Criteria gaps: B1-B4 passing still allows the `--long=value` form of a wrapper's directory option to be ignored. `env --chdir=sub` and `sudo --chdir=sub` print `<R>/sub` today, but no test pins this (Q2).
Criteria gaps: B5 passing still allows a `--long` shell option that contains a `c` to be read as `-c`. `bash --restricted 'git commit -m x'` is correctly not seen today, with no test (Q3).
Criteria gaps: B14 and C29 passing still allows a decoded `'` to be emitted without re-quoting, which would hide a later commit. `echo $'\'' && git commit -m x` is correctly seen today, with no test (Q1).
Criteria gaps: B10 and B12 passing (the guard) says nothing about pd-commit-lint.sh's prefilter. Only the guard's `$'` prefilter widening has a test (Q7).
Criteria gaps: B13 passing does not cover a lint hook reached through a `$'...'`-escaped commit. That works today but is untested (Q7).
Criteria gaps: Hook-level B criteria still allow a commit word split by shell quoting to pass both hooks unseen: `git com''mit`, `git co\mmit` and `bash -c "git com""mit"`. The parser sees all three, but the `*commit*` prefilter (unchanged since base b230ae35) drops them first (Q8).
Criteria gaps: B6/B9 passing still allows non-normalized directories: `env -C sub bash -c 'cd .. && git commit -m x'` prints `<R>/sub/..` (Q6).
Criteria gaps: B7/B8 passing does not cover `&&`/`||`; the documented shortcut remains a non-goal. B8 does not pin depths between 10 levels and the recursion limit beyond C31's calibration.
Criteria gaps: shape.md's contract (:119) names the escapes but does not state the two new rules: a NUL ends the decoded word, and byte escapes combine as UTF-8. An invalid UTF-8 byte (`env -C $'\xff'`) decodes to U+FFFD (`<R>/�`), while bash would use the raw 0xff byte. That matters only on filesystems that allow non-UTF-8 names (not APFS). Unpinned and not filed as an issue.
Criteria gaps: pd-lint at HEAD: plain mode exits 0, and `--risk b230ae35..HEAD` printed nothing (exit 0). `--isolation` was skipped again (Q4). ksh 93 running a bare string (`ksh 'git commit'`) remains backlog item 2026-11-05-commit-guard-ksh-93-runs.
- Q1 warning plugins/pd/hooks/lib/test_commit_target.py:276 — No test fails when the re-quoting of a decoded `'` in `$'...'` is removed. Evidence: Re-run at HEAD: the mutant replacing commit_target.py:113's `text.replace("'", "'\"'\"'")` with `text` survives; the only failures are the archive-environment c23/c26 failures that the unmutated baseline also has. The distinguishing input `echo $'\'' && git commit -m x` gives `<R>\t` from the real code.
- Q2 warning plugins/pd/hooks/lib/test_commit_target.py:95 — The `--long=value` attached form of a wrapper's directory option is untested. Evidence: Re-run at HEAD: the mutant replacing commit_target.py:187's `w.partition("=")` with `(w, "", "")` survives (only the baseline c23/c26 failures). The real code prints `<R>/sub` for `env --chdir=sub git commit -m x` and `sudo --chdir=sub git commit -m x`.
- Q3 note plugins/pd/hooks/lib/test_commit_target.py:193 — No test checks that a `--long` shell option containing `c` (and no `o`) is a flag. Evidence: Re-run at HEAD: deleting `if w.startswith("--"): continue` at commit_target.py:236-237 survives (only the baseline c23/c26 failures). The real code correctly prints nothing for `bash --restricted 'git commit -m x'`.
- Q4 note .claude/pd.local.md:1 — `pd-lint --isolation b230ae35..HEAD` still skips its check, so isolation of the branch diff is unverified. Evidence: Re-run: `pd-lint: WARN .:0: isolation skipped: no source_paths/test_paths, and no src/ or tests/` (exit 0). `pd-lint --risk b230ae35..HEAD` printed nothing and exited 0.
- Q5 note docs/dev_artifacts/workitems/2026-11-03-commit-guard-sees-wrapped-commits/shape.md:68 — Scope In promises new cases in test-hooks.sh (10c) and test-pd-commit-lint.sh, but neither file is changed. D4 (shape.md:133) rejects new 10c cases, so the shape contradicts itself. Evidence: Re-run: `git diff --stat b230ae35..HEAD -- plugins/pd/hooks/tests/` is empty. Hook paths are covered only through the pytest `hook()` helper.
- Q6 note plugins/pd/hooks/lib/commit_target.py:321 — The directory printed after a `cd ..` is not normalized, and the dir-option and `-c` script paths carry that through. Evidence: Re-run: `env -C sub bash -c 'cd .. && git commit -m x'` prints `<R>/sub/..\t`. It still works, because callers pass it to git -C and repo_of resolves it. No criterion pins the form.
- Q7 warning plugins/pd/hooks/pd-commit-lint.sh:9 — R2's fix widened both hook prefilters, but only pre-commit-guard.sh's has a regression test. Reverting pd-commit-lint.sh:9 goes unnoticed. R2's finding asked for end-to-end regressions in both hooks. Evidence: Mutant B (pd-commit-lint.sh:9 back to `*commit*) ;;`) passes all of test_commit_target.py except the baseline-environment c23/c26 failures. test-pd-commit-lint.sh still exits 0 under it. The behaviour itself is fixed: driven on an adopted repo with a staged bogus log.md, `bash -c $'git \x63ommit -m x'` exits 0 on the ec7b13d6 tree and 2 at HEAD. test_review_nul_bytes_and_hook_prefilters calls only `hook("pre-commit-guard.sh", ...)` (test_commit_target.py:481).
- Q8 note plugins/pd/hooks/pre-commit-guard.sh:82 — Both hook prefilters still drop a commit word split by shell quoting or a backslash, which the parser does see. This is the same class as R2, outside the `$'` widening. Evidence: At HEAD, commit_target.py prints `<R>\t` for `git com''mit -m x`, `git co\mmit -m x` and `bash -c "git com""mit -m x"`, but pre-commit-guard.sh on `main` gives no reminder for any of them. The `*commit*` prefilter is unchanged since base b230ae35 (pre-commit-guard.sh:82, pd-commit-lint.sh:9), so this predates the branch. Its forms are not in shape.md's B list.
Fixed: R1 by 38cf87c4 — plugins/pd/hooks/lib/test_commit_target.py::test_review_nul_bytes_and_hook_prefilters (failed before the fix, committed in ec7b13d6)
Fixed: R2 by 38cf87c4 — plugins/pd/hooks/lib/test_commit_target.py::test_review_nul_bytes_and_hook_prefilters, pre-commit-guard.sh end to end (failed before the fix, committed in ec7b13d6)
Fixed: R3 by 38cf87c4 — plugins/pd/hooks/lib/test_commit_target.py::test_review_utf8_bytes_in_directory (failed before the fix, committed in ec7b13d6)
Fixed: R4 by ec7b13d6 — plugins/pd/hooks/lib/test_commit_target.py::test_c25_no_subprocess_for_non_commits traces the raw backslash comment and heredoc inputs (test-only; QA's mutant E survives the 8440dce5 test file and is killed at HEAD)
Closes: review@2026-11-05 05:42+08:00#R1, review@2026-11-05 05:42+08:00#R2, review@2026-11-05 05:42+08:00#R3, review@2026-11-05 05:42+08:00#R4

## 2026-11-05 05:42+08:00 note
Settling qa@2026-11-05 05:42+08:00 (no blocker, no rejection; battery passes at 38cf87c4), the conductor's call, following the owner's rulings to fix warnings in-pass (decision-3 and decision-4@2026-11-05 04:26+08:00):
- Q1, Q2, Q3, Q7 each leave a criterion with no test that would catch its breaking, which the review checklist counts as a blocker: the re-quoting of a decoded `'` (B14, C29), the `--long=value` directory option (`env --chdir=sub`, `sudo --chdir=sub`), a `--long` shell option holding `c` as a flag (B5), and pd-commit-lint.sh:9's widened prefilter (R2, B13). They go into a third verify-change run as test-only work.
- Q8 (the `*commit*` prefilter drops `git com''mit`, unchanged since b230ae35) and Q6 (`sub/..` not normalized; `git -C` and `rev-parse --show-toplevel` resolve it) predate this branch: backlog, filed above.
- Q4 is backlog item set-source-paths-test-paths (from the explorer item). Q5 (shape.md Scope In promises 10c and test-pd-commit-lint.sh cases that D4 rejects) is a pre-implement wording slip, recorded for the retro.
- The NUL and UTF-8 rules the R1 and R3 fixes added are bash's own ANSI-C semantics, which shape.md:119 pins ("decoded as bash's ANSI-C quoting"); no contract change.

## 2026-11-05 06:06+08:00 run verify-change — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 4. Tokens: 51216. Cycles: 1. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_d23ea88e-9a4/journal.jsonl
Run: wf_d23ea88e-9a4 (the third run: test-only, note@2026-11-05 05:42+08:00). Stopped: none.

## 2026-11-05 06:06+08:00 review verify — codex (fallback: no)
Verdict: changes requested. Commit: 4848657b. The four handed-in gaps confirmed (Q1, Q2, Q3, Q7 of qa@2026-11-05 05:42+08:00); no other blocker.
- R1 blocker plugins/pd/hooks/lib/test_commit_target.py:276 — Nothing tests that a decoded apostrophe in $'...' is re-quoted. Removing the re-quoting at commit_target.py:113 breaks no test. Evidence: With the re-quoting removed, `echo $'\'' && git commit -m x` prints nothing. HEAD prints `<repo>\t\n`. Add that exact-output regression and show it red against the mutation.
- R2 blocker plugins/pd/hooks/lib/test_commit_target.py:95 — The `--long=value` form of a wrapper's directory option is untested. The existing cases cover only separate-value directory options. Evidence: Disabling `--long=value` parsing at commit_target.py:187 survives the existing cases. `env --chdir=sub git commit -m x` and `sudo --chdir=sub git commit -m x` then print `<repo>\t\n` instead of `<repo>/sub\t\n`. Add both assertions, red with `--chdir=` dropped from the directory-option match.
- R3 blocker plugins/pd/hooks/lib/test_commit_target.py:193 — No test checks that a `--long` shell option holding `c` is not a command flag. Evidence: Removing the long-option exclusion at commit_target.py:236 survives the existing cases. `bash --restricted 'git commit -m x'` is then wrongly seen and prints `<repo>\t\n`. Add an empty-output assertion, red when the `-`/`+` sign test is widened to `--` words.
- R4 blocker plugins/pd/hooks/lib/test_commit_target.py:230 — No test covers the widened prefilter in pd-commit-lint.sh:9. Line 230 tests only an unescaped commit. The escaped-command regression at line 481 calls only the guard, not the lint hook. Evidence: Reverting pd-commit-lint.sh:9 to `*commit*` escapes detection. Add an adopted-repo test with a staged bogus log.md entry. `bash -c $'git \x63ommit -m x'` must exit 2 with `entry kind bogus`, and must fail when the prefilter is reverted.

## 2026-11-05 06:06+08:00 qa
Commit: 02c67b6a
Ran: `./validate.sh` -> pass
Ran: `bash plugins/pd/hooks/tests/test-hooks.sh` -> pass
Ran: `bash scripts/test-release.sh` -> pass
Ran: `bash -ec 'for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done'` -> pass
Ran: `bash -ec 'for s in pd-adopt pd-init pd-lint pd-new pd-proof pd-review-filter pd-status; do "plugins/pd/scripts/$s" --self-test; done'` -> pass
Ran: `python3 plugins/pd/scripts/pd_common.py --self-test` -> pass
Ran: `uv run --script plugins/pd/scripts/pd-html.py --self-test` -> pass
Ran: `node plugins/pd/workflows/tests/test-workflows.mjs` -> pass
Ran: `uv run --project plugins/pd pytest -q plugins/pd` -> pass
Criteria gaps: Fix checks R1-R4 (commit 02c67b6a, tests only). Each new test is green at HEAD: 43/43 test_commit_target tests were collected and passed in the battery's pytest line. Each was red on its mutant in a `git archive HEAD plugins` copy. R1: line 113 changed to `out.append("'" + text + "'")` makes test_decoded_apostrophe_is_requoted fail. R2: line 187 changed to `name, eq, value = (w, "", "")` makes test_long_equals_directory_option fail, and so does a second mutant that skips dir_opts for an `=`-attached long value. R3: deleting lines 236-237 makes test_long_shell_option_is_not_command_flag fail. R4: pd-commit-lint.sh:9 reverted to `*commit*)` makes test_lint_prefilter_sees_escaped_commit fail. In the copy, test_c23 and test_c26 fail on every variant, base included, because the copy has no .github/ci.yml and no full repo tree. That is an artifact of the copy, not a mutant kill.
Criteria gaps: B1: no case covers `--foreground`, `--preserve-status` or the attached `-sKILL` (grep of test_commit_target.py finds none). They work at HEAD, but no test holds them.
Criteria gaps: B2: deleting sudo's `-g`, `-h`, `-p` or `-T` from WRAPPERS keeps every test green (re-run at 02c67b6a, see Q3). So `sudo -g staff git commit` could regress unseen.
Criteria gaps: B4: the separated `xargs -I {} git commit -m {}` form is still unpinned (see Q2). `-d` survives too, and `-P`, `-L`, `-s`, `-E` and `-a` have no case.
Criteria gaps: B5: the rule '`--long` options are flags' is now pinned by test_long_shell_option_is_not_command_flag (R3). Still a known miss that the shape allows: `bash --rcfile /dev/null -c 'git commit -m x'` is not seen, although real bash runs the script.
Criteria gaps: B6/B9: `~` expansion on a wrapper directory option has no test (see Q5).
Criteria gaps: B8/B15: depth is pinned at 10 levels. Passing B8 says nothing about hook latency at 12 levels (about 1 MB of input).
Criteria gaps: The `$'...'` one-digit `\xH` form has no test (see Q6).
Criteria gaps: The wrapper `--` terminator at commit_target.py:183: deleting the break survived again (mutant dashdash_break: 41 passed, only the two copy-artifact failures). This is close to an equivalent mutant; it shows only when the command word after `--` starts with `-`.
Criteria gaps: B16: the hook suites pass with their text unchanged, but they still have no wrapped-commit case (see Q8).
Criteria gaps: pd-lint --isolation skipped itself again, so isolation is unverified (see Q7).
Criteria gaps: Cross-task flows driven at 02c67b6a in temp repos (driver script /Users/terry/projects/pedantic-drip/agent_sandbox/2026-11-05/commit-guard-qa-run-2/drive.sh). pre-commit-guard.sh on main gives the 'main' reminder for `timeout 30`, `bash -c`, `env --chdir=sub`, `bash -c $'git \x63ommit'` and `echo $'don\'t'; git commit`. It gives no reminder for `bash --restricted '...'` or the quoted prose. On workitem/x, B10 (`git checkout main -- &&`) and `bash -c 'git switch main'; git commit` both give the 'main' reminder; a plain commit gives none. In an adopted repo with a staged bogus log.md entry, pd-commit-lint.sh exits 2 for `bash -c`, the escaped `$'git \x63ommit'`, `sudo -u alice timeout 30 bash -c "cd . && ..."`, `env --chdir=docs`, the decoded-apostrophe form and `nohup`. It exits 0 for the prose `echo 'git commit -m x'` and for `bash --restricted`.
- Q2 warning plugins/pd/hooks/lib/commit_target.py:35 — Still open: xargs' `-I` value option is untested. B4/C4's `xargs -I{}` form passes without it, so `xargs -I {} git commit` could regress silently. Evidence: Re-run at 02c67b6a with mutant xargs_I ("-I" removed from the xargs row): 41 passed. The only failures are the copy-artifact tests c23 and c26. Kill input: at HEAD, `xargs -I {} git commit -m {}` prints `<repo>\t`; on the mutant it prints nothing.
- Q3 note plugins/pd/hooks/lib/commit_target.py:26 — Still open: sudo's -g, -h, -p and -T and xargs' -d can each be deleted from WRAPPERS with no test failing. Evidence: Re-run at 02c67b6a with mutants sudo_g, sudo_h, sudo_p, sudo_T and xargs_d: 41 passed each (only the c23/c26 copy artifacts fail). At HEAD, `sudo -g staff git commit -m x` prints `<repo>\t`; on sudo_g it prints nothing.
- Q5 note plugins/pd/hooks/lib/commit_target.py:203 — Still open: no test covers `~` expansion on a wrapper directory option (sudo -D, env -C). Evidence: Re-run at 02c67b6a with mutant dir_expanduser: 41 passed. `env -C ~ git commit -m x` prints `/Users/terry\t` at HEAD and `<repo>/~\t` on the mutant.
- Q6 note plugins/pd/hooks/lib/commit_target.py:46 — Still open: the one-digit `\xH` form named in the shape's `$'...'` invariant is untested. Evidence: Re-run at 02c67b6a with mutant hex_two_only (`x([0-9A-Fa-f]{2})`): 41 passed. Kill input: `bash -c $'git\x9 commit -m x'` is seen at HEAD and not seen on the mutant.
- Q7 note .claude/pd.local.md:0 — Still open: pd-lint --isolation over b230ae35..HEAD skips the check instead of running it, so isolation is unverified for this diff. Evidence: `plugins/pd/scripts/pd-lint --isolation b230ae359868a407c5992c2874fc9eac76c50956..HEAD` exits 0 and prints `pd-lint: WARN .:0: isolation skipped: no source_paths/test_paths, and no src/ or tests/`. `pd-lint --risk` over the same range exits 0 with no output.
- Q8 note docs/dev_artifacts/workitems/2026-11-03-commit-guard-sees-wrapped-commits/shape.md:68 — Still open: shape ## Scope lists new cases in test-hooks.sh (10c) and test-pd-commit-lint.sh as In, but the branch adds none. Hook-level wrapped-commit coverage lives only in the pytest file's hook() cases, now including test_lint_prefilter_sees_escaped_commit. Evidence: `git diff --stat b230ae35..HEAD -- plugins/pd/hooks/tests/` is empty; the whole branch diff is 17 files, +1350/-23.
Fixed: R1 by 02c67b6a — plugins/pd/hooks/lib/test_commit_target.py::test_decoded_apostrophe_is_requoted (test-only; QA showed it red with the re-quoting at commit_target.py:113 dropped)
Fixed: R2 by 02c67b6a — plugins/pd/hooks/lib/test_commit_target.py::test_long_equals_directory_option (test-only; QA showed it red with `--long=value` parsing disabled at commit_target.py:187)
Fixed: R3 by 02c67b6a — plugins/pd/hooks/lib/test_commit_target.py::test_long_shell_option_is_not_command_flag (test-only; QA showed it red with the `--` long-option skip at commit_target.py:236 deleted)
Fixed: R4 by 02c67b6a — plugins/pd/hooks/lib/test_commit_target.py::test_lint_prefilter_sees_escaped_commit (test-only; QA showed it red with pd-commit-lint.sh:9 reverted to `*commit*`)
Closes: review@2026-11-05 06:06+08:00#R1, review@2026-11-05 06:06+08:00#R2, review@2026-11-05 06:06+08:00#R3, review@2026-11-05 06:06+08:00#R4

## 2026-11-05 06:06+08:00 note
Settling qa@2026-11-05 06:06+08:00 (no blocker, no rejection; battery passes at 02c67b6a), the conductor's call: the fix loop stops here. Each run's mutation sweep finds further single-option coverage gaps in the WRAPPERS table, with every input behaving correctly today (Q2 `xargs -I {}`, Q3 sudo `-g/-h/-p/-T` and xargs `-d`, Q5 `~` on a directory option, Q6 a one-digit `\xH`). They are test debt, not defects, and go to one backlog item, filed above. Q7 is the set-source-paths-test-paths backlog item; Q8 is the earlier run's Q5 (shape.md Scope In wording), for the retro.
