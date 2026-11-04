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
