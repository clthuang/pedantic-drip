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
