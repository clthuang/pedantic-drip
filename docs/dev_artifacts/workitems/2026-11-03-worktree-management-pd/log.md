<!-- Append-only history of 2026-11-03-worktree-management-pd. Entry shapes: plugins/pd/references/log-entries.md. Example:
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."
-->

## 2026-11-03 11:02+08:00 note
Request (verbatim):
> Investigate and design worktree management in pd
Round request (user, 2026-11-03, verbatim):
> proceed to investigate, design and plan for three open backlog items in this round

## 2026-11-03 11:02+08:00 phase triage -> specify
Reason: standard: no module owns worktrees today (implement-tasks, the merger and finishing-branch each touch them), and the criteria need investigation before they can be stated.

## 2026-11-03 11:08+08:00 decision
Q: worktree management in pd: which problems should this work item solve? (Clarify: the right problem, and what success looks like)
A (user, verbatim): "One cleanup script (Recommended), Show leftovers in pd-status (Recommended)"
Not chosen: removing worktrees inside the workflow; tidying this repo's `.pd-worktrees/` remnant.

## 2026-11-03 11:19+08:00 review calvin cycle 1 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/calvin-cycle-1.md. Verdict: 7 blockers, 9 warnings, 10 notes; all 26 answered and `## Requirements` rewritten (sections `pd-worktrees` and Callers added).
- R1 blocker shape.md:59 — the wrong-test move and the no-branch-delete rule; the script never deletes task branches, its callers do (wrong-test `-D` after it).
- R2 blocker shape.md:76 — the wrong-test move's per-task scope; `--task <n>` added (B8).
- R3 blocker shape.md:62 — a dirty worktree at the wrong-test move; exit 1, the user keeps or discards, and only the conductor forces on "discard".
- R4 blocker shape.md:78 — Finish's PR path deletes `workitem/<id>` first (`finishing-branch/SKILL.md:30`, checked); a work item is its directory now, not its branch (B10).
- R5 blocker shape.md:40 — strays can't be tied to one work item; they are repository-wide, deleted with `-d` only.
- R6 blocker shape.md:100 — strays need no ancestry check now, so `pd-status` keeps two git calls.
- R7 blocker shape.md:99 — a gone worktree is cleared by its path: `git worktree remove <gone path>` clears that entry only (scratch repo, git 2.54.0, 2026-11-03), B5.
To the user: none (row 26, why a shared script, is answered from the owner's Clarify ruling and the "Done means" line).
To the conductor (wording or consistency, each answered by a revision):
- rows 8, 15: the fixer's own forced removal stays (non-goal); strays deleted with `-d`.
- rows 9, 10, 11, 12, 14: the Callers section: exit 1 and exit 2 handling, Execute after every run end, all of `<id>`'s worktrees, the exit-code rule.
- rows 13, 18, 19, 25: five worktree states, dead-session locks, a task worktree defined by its branch wherever it lives, the main checkout case (B13).
- rows 16, 17, 20, 21, 22, 23, 24: any `## Now` line counts (B9), stale lines are a non-goal, the `no work item` reason, B14's line format and order, every session-start source (B16), `pd-status`'s docstring in scope, the Claude Code page sections named.

## 2026-11-03 11:28+08:00 review calvin cycle 2 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/calvin-cycle-2.md. Verdict: 3 blockers, 10 warnings, 11 notes; cycle 1: 22 rows answered, 4 partly (3, 24, 25, 26), now answered. All 24 answered and `## Requirements` revised.
Closes: review@2026-11-03 11:19+08:00#R1, review@2026-11-03 11:19+08:00#R2, review@2026-11-03 11:19+08:00#R3, review@2026-11-03 11:19+08:00#R4, review@2026-11-03 11:19+08:00#R5, review@2026-11-03 11:19+08:00#R6, review@2026-11-03 11:19+08:00#R7
- R1 blocker shape.md:66 — abandon's work item directory lives only on its branch; abandon calls the script before switching off it, and a known work item now includes one with only branches.
- R2 blocker shape.md:42 — `-d` against `HEAD` keeps strays of an abandoned branch; a stray is deleted when another branch contains its tip (loses no commit), else kept and printed.
- R3 blocker shape.md:91 — a stray's line has no id; it prints `-`.
To the user: none.
To the conductor (wording or consistency, each answered by a revision):
- rows 4, 5, 6, 7, 8, 9, 10: Callers: Execute calls after the line is cleared; run-in-flight exit 1 stops for the user; only a kept worktree's branch stays, the rest goes on; after "discard" the caller goes on; the wrong-test move offers discard or stop, never keep-and-continue.
- rows 11, 12, 13, 15, 16, 17, 18: state precedence; the main checkout counts as a task worktree; exit 2 on a mid-way git failure with the lines printed so far; "removed" wording; strays only without `--task` (B8); another run's strays; strays come from any Workflow-tool agent.
- rows 14, 19, 20, 21: the gone-entry check cited (scratch repo, git 2.54.0); "done" excuses anything reported and kept; one line per leftover, a held branch not repeated; the dead-lock release quoted from the worktrees page.
- rows 22, 23, 24: only work items visible in this checkout are judged (B15); the section opens with what to run; the four docs that list scripts named (grep for `pd-review-filter`).

## 2026-11-03 11:34+08:00 review calvin cycle 3 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/calvin-cycle-3.md. Verdict: 2 blockers, 7 warnings, 13 notes; cycle 2: 21 rows answered, 3 partly (9, 13, 19), and cycle 1's row 26 open; all now answered. This is the third cycle: the cap.
Closes: review@2026-11-03 11:28+08:00#R1, review@2026-11-03 11:28+08:00#R2, review@2026-11-03 11:28+08:00#R3
- R1 blocker shape.md:41 — a task branch made its id known, so `no work item` could never apply; a known work item is now its directory in this checkout, and `no work item` also needs no `workitem/<id>` branch.
- R2 blocker shape.md:44 — two strays sharing a tip would vouch for each other; only a branch that isn't a stray counts (B19).
To the user: whether this revision ends the loop (the cap question).
To the conductor (each answered by the same revision):
- rows 3, 5, 21: the id must have its directory here; `pd-worktrees --strays [--remove]` clears strays with no work item; why every stray qualifies.
- rows 4, 10, 11, 19: B14's first line names both commands and "by hand" for other branches; the state shows in `pd-worktrees <id>`; the section is in the full report only.
- rows 6, 7: abandon calls only when the user accepts cleanup; its run-in-flight check finds nothing, a live run's worktree is `locked`.
- rows 8, 9, 22: any kept worktree of a re-run task stops the wrong-test move; Execute asks at step 5 and exit 2 stops before step 6.
- rows 12, 13, 14, 15: no question without a dirty one; a discarded worktree's branch is deleted; "unexpected" git failures defined; Done excepts anything reported kept.
- rows 16, 17, 18, 20: Goals say clean or gone and name strays; a main checkout on a task branch is a real leftover; the removal-site grep is cited in Why; cycle 1's row 26 answered by "What they cost".
- pd-status's branch call adds `workitem/*`, which the `no work item` rule needs.

## 2026-11-03 11:34+08:00 capped specify
Deferred: none
Follow-ups: none
Decisions:
- whether the revision answering cycle 3's blockers ends the calvin loop, or a fourth cycle runs: asked of the user.
Assumptions: none
Closes: review@2026-11-03 11:34+08:00#R1, review@2026-11-03 11:34+08:00#R2

## 2026-11-03 11:58+08:00 decision
Q: does the revision answering calvin cycle 3 end the calvin loop?
A (user, verbatim): "Accept the fixes (Recommended)"
answers: capped@2026-11-03 11:34+08:00

## 2026-11-03 11:59+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Signed off"

## 2026-11-03 11:59+08:00 phase specify -> design
Criteria signed off (decision above); calvin loop capped at cycle 3, ended by the owner (decision@2026-11-03 11:58+08:00).

## 2026-11-03 12:10+08:00 note
Grounding: codebase-explorer dispatch (designing step 2), 14 findings with file:line: pd-status report() blocks and early returns (pd-status:86-129), pd_common.git and sections (pd_common.py:137-165, 228), sibling-script conventions, the session-start awk (pd-session-start.sh:43-51) and its test, CI's explicit script and pytest lists (ci.yml:34-42), no existing worktree helper, three run-in-flight parsers (pd-lint:34, pd-stop-gate.sh:23).

## 2026-11-03 12:21+08:00 review design — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, on commit 823fe8c7 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/review-brief-1.md). Verdict: not approved; 10 blockers. Each claim checked before acting; all ten hold (R1 and R2 also probed on git 2.54.0).
- R1 blocker shape.md:228 — a stray deleted by name with `-D` after the check could lose a commit pushed to it in between; deleted now by `git update-ref -d <ref> <checked tip>`, which refuses a moved branch (probed: exit 1, branch kept).
- R2 blocker shape.md:142 — newline-split porcelain can't carry a path holding a newline; parsed with `-z`, shown escaped.
- R3 blocker shape.md:172 — git ran from the invoking checkout, which may be a worktree being removed; every call now runs from the main checkout (D6).
- R4 blocker shape.md:168 — exit 2 "a git failure" contradicted the refusal-is-exit-1 rule; WorktreesCLI now pins refusals as `kept (<state>)`, exit 1, and exit 2 as every other failure.
- R5 blocker shape.md:162 — a clean worktree holding a submodule had no outcome; it prints `kept (clean)`, and the ask treats it like a dirty one.
- R6 blocker shape.md:181 — the section couldn't show `locked`, which the dead-lock edge case asks of both scripts; a locked worktree's path is followed by ` (locked)`, from the same porcelain record.
- R7 blocker shape.md:124 — CallerSteps and pd-status's branch query had no edge; both drawn, and GitSurface split per script.
- R8 blocker shape.md:252 — no cross-file invariants or proving commands; four named, each with its test file, and the three files on CI's pytest line.
- R9 blocker shape.md:231 — D5 named no rejected alternative; a reference file and per-caller copies rejected, with evidence.
- R10 blocker shape.md:240 — the porcelain-drift row had no evidence; replaced by the `-z` version floor, with the hypotheticals moved to the notes.
Fix cycle 1 of 3: `## Design` rewritten; pd-lint and `phase-gate.sh design` pass. Next: a scoped re-review.

## 2026-11-03 12:34+08:00 review design, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to R1 to R10 and the edit 823fe8c7..807a4fb9 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/review-brief-2.md). R1 to R10 resolved; four new blockers in the diff, each checked (N1 and N2 probed on git 2.54.0 and Python 3.13).
Closes: review@2026-11-03 12:21+08:00#R1, review@2026-11-03 12:21+08:00#R2, review@2026-11-03 12:21+08:00#R3, review@2026-11-03 12:21+08:00#R4, review@2026-11-03 12:21+08:00#R5, review@2026-11-03 12:21+08:00#R6, review@2026-11-03 12:21+08:00#R7, review@2026-11-03 12:21+08:00#R8, review@2026-11-03 12:21+08:00#R9, review@2026-11-03 12:21+08:00#R10
- N1 blocker shape.md:167 — `update-ref -d` through a symbolic `worktree-wf_*` ref deletes its target (probed: `workitem/x` deleted); `--no-deref` added (probed: only the alias goes).
- N2 blocker shape.md:142 — git()'s text mode turns `\r` into `\n` (probed), so two paths could collide; worktrees() reads bytes.
- N3 blocker shape.md: — update-ref skips git branch's checked-out check; the list is re-read before each delete, and the one-call window left loses no commit (risk row).
- N4 blocker shape.md:177 — pd-worktrees had two contract blocks; GitSurface folded into its one block.
Fix cycle 2 of 3: `## Design` revised; pd-lint and `phase-gate.sh design` pass. Next: a scoped re-review of N1 to N4.

## 2026-11-03 12:38+08:00 review design, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to N1 to N4 and the edit 807a4fb9..7ab8d2a2 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/review-brief-3.md). N1, N2 and N4 resolved; N3 open; nothing new in the diff.
Closes: review@2026-11-03 12:34+08:00#N1, review@2026-11-03 12:34+08:00#N2, review@2026-11-03 12:34+08:00#N4
- R1 blocker shape.md:239 — still open from review@2026-11-03 12:34+08:00#N3: a worktree can check out a stray, tip unchanged, between the final re-read and `update-ref --no-deref -d`, deleting a branch then held.
Rejects: R1 — no git command closes that window: `git branch -d/-D` makes the same check-then-delete in two steps (builtin/branch.c: `branch_checked_out()`, then the ref delete), and a ref lock doesn't block another worktree's checkout, which writes only that worktree's HEAD. The design matches git's own guarantee, and the delete succeeds only at a tip a non-stray branch contains, so no commit is lost (risk row). Proposed for the user's decision.

## 2026-11-03 12:40+08:00 decision
Q: accept the one-call window in which a stray checked out after the re-read is deleted under its worktree (no commit lost), as git's own check-then-delete guarantee?
A (user, verbatim): "Accept the window (Recommended)"
Closes: review@2026-11-03 12:34+08:00#N3, review@2026-11-03 12:38+08:00#R1

## 2026-11-03 12:40+08:00 phase design -> create-plan
Design review loop ended: R1 to R10 and N1, N2, N4 resolved by revision; N3 closed by the owner (decision above).

## 2026-11-03 12:49+08:00 review plan — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, the test-case review of plan.md at a1e6bf56 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/plan-review-brief-1.md). Not approved: six blockers, each checked against plan.md and the code (pd-status:110-125 for the report blocks, abandon-workitem.md:12 for the unconditional -D).
- R1 blocker plan.md:78 — C32 to C35 don't prove B18's exit handling: no run-in-flight stop in C32, no exit-2 stop or kept-branch exclusion in C34 and C35.
- R2 blocker plan.md:31 — C6, C8, C10 and C14 assert success messages, not the ref, directory and registration state.
- R3 blocker plan.md:64 — C29's fake fails every git call, so a failing `branch --list` after a good `worktree list` goes untested.
- R4 blocker plan.md:60 — C25 populates no other report section, so "last section" can't catch a misplaced block; C26 seeds no leftover in the no-items report and has no unadopted variant.
- R5 blocker plan.md:65 — C30's single work item can't catch per-item git calls.
- R6 blocker plan.md:66 — C31's string check misses an argv-list `worktree list` call and doesn't prove the helpers are called.
Fix cycle 1 of 3: plan.md revised (C6, C8, C10, C14, C25, C26, C29 to C35); pd-lint and `phase-gate.sh create-plan` pass. Next: a scoped re-review of R1 to R6.

## 2026-11-03 12:52+08:00 review plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to R1 to R6 and the edit a1e6bf56..ccd73d27 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/plan-review-brief-2.md). R1 to R6 resolved; one new blocker in the diff, checked (pd-status already makes its own git calls via pd_common.py:144-146, so per-type counts don't bound the total).
Closes: review@2026-11-03 12:49+08:00#R1, review@2026-11-03 12:49+08:00#R2, review@2026-11-03 12:49+08:00#R3, review@2026-11-03 12:49+08:00#R4, review@2026-11-03 12:49+08:00#R5, review@2026-11-03 12:49+08:00#R6
- N1 blocker plan.md:65 — the revised C30 lost the absolute "two calls added" bound: a fixed extra git call per report passes it.
Fix cycle 2 of 3: C30 now compares its logged calls with the fork point's `pd-status` on the same fixture, plus exactly the two listings; pd-lint and `phase-gate.sh create-plan` pass. Next: a scoped re-review of N1.

## 2026-11-03 12:54+08:00 review plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to N1 and the edit ccd73d27..99fe91b7 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/plan-review-brief-3.md). N1 resolved; one new blocker in the diff, checked (`git merge-base main HEAD` is HEAD once merged; CI runs on pushes to main, ci.yml:4-5).
Closes: review@2026-11-03 12:52+08:00#N1
- N2 blocker plan.md:65 — C30's baseline from `git merge-base main HEAD` is the new `pd-status` itself after the merge, so a correct implementation fails on main.
Fix cycle 3 of 3: C30's baseline is now a literal multiset (`pd-status` makes one git call today, `rev-parse --show-toplevel`, logged at b230ae35); pd-lint and `phase-gate.sh create-plan` pass. The same moving baseline sits in the commit guard's C25; fixed there by a backward move.

## 2026-11-03 12:57+08:00 review plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to N2 and the edit 99fe91b7..0c2f2314 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/plan-review-brief-4.md). N2 resolved; one new blocker in the diff, checked against shape.md:196-197.
Closes: review@2026-11-03 12:54+08:00#N2
- M1 blocker plan.md:65 — C30's literal `branch --list` call lacks the `--format=%(refname:short)` shape.md:197 pins, so a compliant implementation fails the exact match.

## 2026-11-03 12:57+08:00 capped plan
The plan review used its three fix cycles (review@2026-11-03 12:49+08:00, fix cycles at 12:49, 12:52, 12:54); M1 arrived in the third cycle's re-review.
Deferred: none
Follow-ups: none
Decisions:
- whether M1's fix past the cap (C30's literal now carries shape.md:197's argument list, `branch --list pd/* workitem/* worktree-wf_* --format=%(refname:short)`) ends the review loop: asked of the user.
Assumptions:
- A1: the fix is mechanical — it copies shape.md:197's argv into C30's literal and changes no other case.

## 2026-11-03 13:40+08:00 decision
Q: does M1's fix past the cap (C30's literal carrying shape.md:197's argument list) end the plan review loop?
A (user, verbatim): "Accept the fix (Recommended)"
answers: capped@2026-11-03 12:57+08:00
Closes: review@2026-11-03 12:57+08:00#M1

## 2026-11-03 13:40+08:00 phase create-plan -> implement
Plan review loop ended: R1 to R6, N1 and N2 resolved by revision; M1 closed by the owner (decision above). Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 13:40+08:00 note
Goal-run offer skipped: the owner scoped this round to investigate, design and plan the three backlog items, with no Execute ("proceed to investigate, design and plan for three open backlog items in this round").

## 2026-11-03 18:57+08:00 review design and plan, simplification — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, a simplification review of shape.md ## Design and plan.md at 4c3b1edc (the owner's ask: "use agents to code review, QA, and simplify implementation without compromising functionality"; brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/simplify-brief-1.md). Two cuts proposed, no blocker.
- R1 warning plan.md:48 — C23 replays every `wt` call of C1 to C22 under the logging git; instead every `wt` call runs under it and checks the must-nots right after, the fakes logging too. No behavioral assertion goes; C23 stays as the guard's negative control.
- R2 warning shape.md:179 — list each stray's ref and tip in one `git for-each-ref --format='%(refname) %(objectname)'` and drop the per-stray `git rev-parse`. Checked on git 2.54.0: the listed object id equals `rev-parse` for a plain and a symbolic `worktree-wf_*` ref, and `update-ref --no-deref -d` with it removes only the alias, its target kept. Containment, the re-read and the compare-and-delete are unchanged, so review@2026-11-03 12:21+08:00#R1 and review@2026-11-03 12:34+08:00#N1/#N3 stay answered.

## 2026-11-03 18:57+08:00 phase implement -> design (back)
Reason: the simplification review above (R1, R2). Nothing has executed.
Invalidates: shape.md ## Design (the stray listing, GitSurface (pd-worktrees)); plan.md from_shape, C23.

## 2026-11-03 19:01+08:00 review design and plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, the QA pass on the simplification 4c3b1edc..a0141f62 (brief agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/simplify-qa-brief-1.md). Approved, no issues: Requirements byte-identical, from_shape current, every B still covered (B1-B13 by C1-C13, B14 by C25/C26/C30/C31, B15-B17 by C27-C29, B18 by C32-C36, B19 by C14); the guard now runs on every `wt` call with C23 as its negative control; the combined stray listing keeps containment, the re-read and `--no-deref` compare-and-delete, so the protections at log.md review@2026-11-03 12:21+08:00#R1 and 12:34+08:00#N1/#N3 and the owner's accepted window hold.

## 2026-11-03 19:01+08:00 phase design -> create-plan
Simplification applied to ## Design and QA-approved (review above); design exit check passed.

## 2026-11-03 19:01+08:00 phase-2 create-plan -> implement
Plan exit check passed (phase-gate.sh create-plan, pd-lint clean); plan.md from_shape matches shape.md.

## 2026-11-03 19:24+08:00 phase implement -> design (back)
Reason: calvin on plan.md, the owner's rule between plan and execution (52 questions, the conductor adjudicating as author). Four answers change ## Design: how a failed compare-and-delete is told from a git failure, `shown()` escaping a backslash and `\r`, which checkout's files `pd-worktrees` reads when run from a task worktree, and what the ask says about a discarded worktree's branch at Execute. Nothing has executed.
Invalidates: shape.md ## Design (WorktreeHelpers.shown, WorktreesCLI, CallerSteps); plan.md.

## 2026-11-03 19:26+08:00 note
Calvin on plan.md (the owner's rule before Execute): one pass in report mode, 52 questions, adjudicated by the conductor as the plan's author; 46 fixed, 6 answered. Fixed:
- ## Design: a failed `update-ref` is the refusal only when the stray, read again, points elsewhere (gone: skipped; otherwise exit 2); `shown()` escapes backslash, newline, carriage return and tab, backslash first; the work item's directory and README are read in the main checkout, and removals follow porcelain order; `--remove` with nothing prints `no worktrees for <id>`, exit 0; `<id> --strays` is exit 2; at Execute a discarded worktree's branch stays (Execute deletes no branch).
- plan.md shared terms: `task_worktree` takes an id and a path; stdout splits on `\n` only; "expect" vs "exactly" vs "in order"; paths as the porcelain reports them; literal work item ids; the guard reads only its own call's log lines and matches whole arguments; the fakes log JSON argv lines and make their extra calls unlogged through the real git.
- Cases: C6 makes its own commit on `workitem/<id>`; C7 uses the shared task number; exit codes on C7, C20, C22; C11, C12, C14 gain the `--remove`-with-nothing, `<id> --strays` and plain `--strays` forms; C17 explains why porcelain order proves the main-checkout cwd; C18 commits the submodule; C22's printed `\r`; C23 a `workitem/*` vector; C24 the CHANGELOG line; C26 builds adopted repositories; C27's run line is not the first; C28 the announcement line, the awk comment and `test-pd-session-start.sh`; C29 compares against a real-git run; C30 item counts; C31 checks call arguments only; new C37 for `pd-status --self-test` and its docstring; Task 3's step spans and literal substrings; C32 to C36 pinned to specific lines (`README_FOR_DEV.md:230-231`, `architecture.md:79`, `commands-reference.md:41`, the `--self-test` loop left alone per D3).
Answered: `for-each-ref --contains` reads only local branches (remote-tracking refs aren't `refs/heads/`); a lock by a live session is kept like any lock; the must-not on forcing is a lasting rule (the guard stays in the suite); a cross-task branch name clash can't happen (one `<id>`, one number); C30's literal multiset is the call budget; the live caller flows are Verify's QA.

## 2026-11-03 19:27+08:00 phase design -> create-plan
Calvin's Design fixes applied (note above); design exit check passed.

## 2026-11-03 19:27+08:00 phase-2 create-plan -> implement
Plan exit check passed (phase-gate.sh create-plan, pd-lint clean); from_shape matches shape.md.

## 2026-11-03 19:57+08:00 run implement-tasks — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 6. Tokens: 79674. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_5508effe-a3f/journal.jsonl
Commit: 915a9fff
- task 1: merged, proof pass, cycles 0, branch pd/2026-11-03-worktree-management-pd/task-1
  case_map: C1=plugins/pd/scripts/test_pd_worktrees.py::test_c1_list_every_state, C2=plugins/pd/scripts/test_pd_worktrees.py::test_c2_remove_clean, C3=plugins/pd/scripts/test_pd_worktrees.py::test_c3_dirty_is_kept, C4=plugins/pd/scripts/test_pd_worktrees.py::test_c4_locked_and_gone_is_kept, C5=plugins/pd/scripts/test_pd_worktrees.py::test_c5_gone_cleared_by_path, C6=plugins/pd/scripts/test_pd_worktrees.py::test_c6_strays_by_containment, C7=plugins/pd/scripts/test_pd_worktrees.py::test_c7_other_worktrees_untouched, C8=plugins/pd/scripts/test_pd_worktrees.py::test_c8_only_the_named_task, C9=plugins/pd/scripts/test_pd_worktrees.py::test_c9_run_in_flight_removes_nothing, C10=plugins/pd/scripts/test_pd_worktrees.py::test_c10_work_item_branch_gone, C11=plugins/pd/scripts/test_pd_worktrees.py::test_c11_nothing_to_show, C12=plugins/pd/scripts/test_pd_worktrees.py::test_c12_usage_errors, C13=plugins/pd/scripts/test_pd_worktrees.py::test_c13_main_checkout_on_task_branch, C14=plugins/pd/scripts/test_pd_worktrees.py::test_c14_strays_without_a_work_item, C15=plugins/pd/scripts/test_pd_worktrees.py::test_c15_stray_moved_before_delete, C16=plugins/pd/scripts/test_pd_worktrees.py::test_c16_newline_in_path, C17=plugins/pd/scripts/test_pd_worktrees.py::test_c17_invoked_from_inside_a_removed_worktree, C18=plugins/pd/scripts/test_pd_worktrees.py::test_c18_clean_worktree_with_submodule, C19=plugins/pd/scripts/test_pd_worktrees.py::test_c19_git_failure_is_exit_2, C20=plugins/pd/scripts/test_pd_worktrees.py::test_c20_symbolic_ref_stray, C21=plugins/pd/scripts/test_pd_worktrees.py::test_c21_stray_taken_by_a_worktree, C22=plugins/pd/scripts/test_pd_worktrees.py::test_c22_carriage_return_in_path, C23=plugins/pd/scripts/test_pd_worktrees.py::test_c23_guard_is_not_vacuous, C24=plugins/pd/scripts/test_pd_worktrees.py::test_c24_ci_and_changelog; greens: plugins/pd/scripts/test_pd_worktrees.py::test_c23_guard_is_not_vacuous; skipped: none
- task 2: merged, proof pass, cycles 0, branch pd/2026-11-03-worktree-management-pd/task-2
  case_map: C25=plugins/pd/scripts/test_pd_status_leftovers.py::test_c25_every_reason_in_order, C26=plugins/pd/scripts/test_pd_status_leftovers.py::test_c26_no_leftovers_and_early_reports, C27=plugins/pd/scripts/test_pd_status_leftovers.py::test_c27_run_in_flight_and_other_branch_items_not_listed, C28=plugins/pd/scripts/test_pd_status_leftovers.py::test_c28_session_start_passes_the_section plugins/pd/scripts/test_pd_status_leftovers.py::test_c28_comment_and_hook_test, C29=plugins/pd/scripts/test_pd_status_leftovers.py::test_c29_git_failure_drops_the_section plugins/pd/scripts/test_pd_status_leftovers.py::test_c29_outside_git, C30=plugins/pd/scripts/test_pd_status_leftovers.py::test_c30_git_cost_is_two_calls, C31=plugins/pd/scripts/test_pd_status_leftovers.py::test_c31_shared_helpers_only, C37=plugins/pd/scripts/test_pd_status_leftovers.py::test_c37_self_test_and_docstring (C28 and C29 parametrized: 4 session sources, 3 failing git calls); greens: plugins/pd/scripts/test_pd_status_leftovers.py::test_c26_no_leftovers_and_early_reports plugins/pd/scripts/test_pd_status_leftovers.py::test_c27_run_in_flight_and_other_branch_items_not_listed plugins/pd/scripts/test_pd_status_leftovers.py::test_c29_outside_git; skipped: none
- task 3: merged, proof pass, cycles 0, branch pd/2026-11-03-worktree-management-pd/task-3
  case_map: C32=plugins/pd/scripts/test_worktree_callers.py::test_c32_implementing_step_5_clears_worktrees_after_the_run, C33=plugins/pd/scripts/test_worktree_callers.py::test_c33_wrong_test_bullet_removes_by_task_before_branch_delete, C34=plugins/pd/scripts/test_worktree_callers.py::test_c34_finishing_step_9_uses_pd_worktrees_before_branch_delete, C35=plugins/pd/scripts/test_worktree_callers.py::test_c35_abandon_step_3_uses_pd_worktrees_before_switching_off, C36=plugins/pd/scripts/test_worktree_callers.py::test_c36_docs_name_pd_worktrees; greens: none; skipped: none

## 2026-11-03 19:58+08:00 phase implement -> verify
Implement exit check passed (phase-gate.sh implement: all three plan tasks on merged, proof pass lines). Re-run on the branch after the merges: the three proving files 44 passed; CI's test steps (hook suites, phase-gate, eight self-tests, test-workflows.mjs, the pytest line: 54 passed), test-hooks.sh 24/24 and validate.sh all pass. `pd-worktrees 2026-11-03-worktree-management-pd` on this repository lists the run's three clean task worktrees, exit 0; `--strays` lists none.

## 2026-11-04 14:09+08:00 run verify-change — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 4. Tokens: 55342. Cycles: 1. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_2b4646db-f10/journal.jsonl
Run: wf_2b4646db-f10. Stopped: none.

## 2026-11-04 14:09+08:00 review verify — codex (fallback: no)
Verdict: changes requested. Commit: ef16b893.
- R1 blocker plugins/pd/scripts/pd-worktrees:56 — Ambiguous short ref names can make a stray vouch for itself, allowing deletion of its unique commits.
- R2 blocker plugins/pd/skills/implementing/SKILL.md:33 — The wrong-test cleanup invocation lacks the required hard stop on exit 2.
- R3 blocker plugins/pd/scripts/pd-worktrees:112 — A refused removal does not refresh the worktree's lock or prunable state.
- R4 blocker plugins/pd/scripts/pd-worktrees:94 — Empty cleanup bypasses the run-in-flight guard.
- R5 blocker plugins/pd/scripts/pd-worktrees:64 — A failed post-deletion lookup is silently treated as an absent branch.
- R6 blocker plugins/pd/scripts/test_pd_worktrees.py:120 — C3 does not prove B3's clean-worktree removal in the mixed clean/dirty case.
- R7 blocker plugins/pd/scripts/test_pd_status_leftovers.py:129 — C27, green at its first commit, does not prove B15's filtering behavior.
- R8 blocker plugins/pd/scripts/test_pd_status_leftovers.py:47 — Remove the unused retro option of make_item() and its file-writing branch.
- R9 warning plugins/pd/scripts/pd-status:90 — The implemented signature differs from the contract.
Rejects: review@2026-11-04 14:09+08:00#R1 — The finding is real, but the fix needs a contract change, so it goes to the user. shape.md GitSurface pins `--format=%(refname:short)` for `git for-each-ref --contains <tip> refs/heads/` (read at plugins/pd/scripts/pd-worktrees:56). The short name is ambiguous when a same-named tag exists. LeftoverSection in shape.md, via pd-status leftovers() at plugins/pd/scripts/pd-status:~113, has the same pinned `branch --list --format=%(refname:short)`. Proposed change: pin `%(refname)` in both places, strip `refs/heads/` in code, and compare full refs throughout. I did not edit shape.md, and I did not make the code diverge from the pinned format.

## 2026-11-04 14:09+08:00 qa
Commit: 44433ea8
Ran: `./validate.sh` -> pass
Ran: `bash plugins/pd/hooks/tests/test-hooks.sh` -> pass
Ran: `bash scripts/test-release.sh` -> pass
Ran: `bash -ec 'for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done'` -> pass
Ran: `bash -ec 'for s in pd-adopt pd-init pd-lint pd-new pd-proof pd-review-filter pd-status; do "plugins/pd/scripts/$s" --self-test; done'` -> pass
Ran: `python3 plugins/pd/scripts/pd_common.py --self-test` -> pass
Ran: `uv run --script plugins/pd/scripts/pd-html.py --self-test` -> pass
Ran: `node plugins/pd/workflows/tests/test-workflows.mjs` -> pass
Ran: `uv run --project plugins/pd pytest -q plugins/pd` -> pass
Criteria gaps: Fix check, R2-R5 hold: I exported trees at cfa37f76 and 44433ea8 (git archive of plugins/pd) and ran the four new tests in each. At cfa37f76 all four are red, each for the reason its finding names. C33: the bullet has no 'exit 2'/'hard stop'. R3: printed 'kept (clean)', not 'kept (locked)'. R4: printed 'no worktrees for <id>', not the run-in-flight line. R5: exit 0 with empty stderr. At 44433ea8 all four are green.
Criteria gaps: Fix check, R6 and R7 hold: the strengthened C3 and C27 are green at both commits, as expected for test-only fixes. Each now kills the mutant its finding describes. A pd-worktrees mutant that prints 'removed' without calling `git worktree remove` fails C3 (11 failures in total). A pd-status mutant that exits 1 with empty stdout fails C27.
Criteria gaps: Fix check, R8 holds: cfa37f76 deletes the `retro=False` parameter and the retro.md branch from make_item(), and no call site passes retro=.
Criteria gaps: B1/C1 pass would still allow `pd-worktrees <id>` in list mode to print a wrong state for the main checkout. `main checkout` is tested only under --remove (C13, test_pd_worktrees.py:261).
Criteria gaps: B3/C3 pass, together with the Risks row 'turns dirty between the state check and remove', would still allow a wrong state when the refusal comes from new dirt rather than a new lock. Only the lock race is simulated (test_refused_removal_reads_lock_state_again). The re-read shares state_of(), so the risk is low.
Criteria gaps: B6/B19 pass would still allow a `worktree-wf_*` branch that a worktree holds to count as the non-stray branch that vouches for a stray. This matches the Terms definition literally, but no test pins it either way.
Criteria gaps: B12/C12 pass would still allow `..` and `.` to be accepted as known work items. See Q3: the mutant that deletes the `"/"` guard still survives all 27 tests in test_pd_worktrees.py.
Criteria gaps: B14/C25 pass would still allow a branch held by a listed worktree to be listed a second time. That covers a held `worktree-wf_*` branch, which would show as `stray branch`. See Q4: the mutant `sorted(branches)` survives all 42 tests in test_pd_worktrees.py and test_pd_status_leftovers.py.
Criteria gaps: B16/C28 pass would still allow the hook to drop or truncate the section when pd-status prints many leftover lines. Only a single leftover is tested.
Criteria gaps: B18/C32-C35 pass would still allow caller prose that reads ambiguously, because the tests check literal substrings in order and not behaviour. Example: abandon's 'any other `pd/<id>/task-*` branches' depends on the conductor reading the kept list.
Criteria gaps: B18 pass would still allow callers to invoke a bare `pd-worktrees`, which is not on PATH (see Q6).
Criteria gaps: Worktree paths are covered only for \n and \r (C16, C22). A tab or backslash in a path passing through `shown()` is untested end to end.
Criteria gaps: End-to-end flow in a scratch repo across tasks 1-3 behaved as shape.md says. The flow: an Execute leaves 3 task worktrees (one dirty) and a stray. pd-status lists 3 `worktree after its run` lines plus the stray, and the session-start hook on resume includes the section. `pd-worktrees --remove` removes 2, keeps the dirty one, deletes the stray, and exits 1. A run in flight makes `--remove --task 3` print the line and exit 1, and pd-status omits that worktree. After abandoned status, --force discard, a second --remove and `branch -D` of all three, pd-status has no Leftover worktrees section. All five B12 usage errors exit 2 with a message on stderr. Not driven: the conductor's AskUserQuestion step, and Finish's `-d` path with a real PR.
- Q1 warning plugins/pd/scripts/conftest.py:1 — Still open. pd-lint reports a security risk signal that has no matching `risk: [security]` tag on the work item.
- Q2 warning plugins/pd/scripts/pd_common.py:1 — Still open. pd-lint reports a security risk signal that has no matching `risk: [security]` tag on the work item.
- Q3 warning plugins/pd/scripts/pd-worktrees:91 — Still open. `..` and `.` pass the known-work-item check, so `pd-worktrees .. --remove` deletes strays and exits 0 instead of exiting 2.
- Q4 warning plugins/pd/scripts/test_pd_status_leftovers.py:74 — Still open. test_c25_every_reason_in_order cannot fail on the rule 'a branch a listed worktree holds isn't listed again'.
- Q6 note plugins/pd/skills/implementing/SKILL.md:25 — Still open. The caller steps invoke bare `pd-worktrees`, which is not on PATH, while the same files use `${CLAUDE_PLUGIN_ROOT}/scripts/...` for phase-gate.sh.
- Q7 note plugins/pd/scripts/pd-worktrees:96 — Still open. `pd-worktrees --strays --remove --task 1` is accepted, empties the stray set, does nothing and exits 0.
- Q8 note plugins/pd/scripts/pd-status:90 — Still open. LeftoverSection names `leftovers(root, art, items)`, but the code defines `leftovers(root, items)`.
- Q9 note .:0 — Still open. The isolation check did not run on the branch diff.
- Q10 warning plugins/pd/hooks/lib/trace.jsonl:1 — Fix commit 44433ea8 also committed a debugging trace file into shipped plugin source. The file is unrelated to R2-R5.
Fixed: R2 by 44433ea8 — plugins/pd/scripts/test_worktree_callers.py::test_c33_wrong_test_bullet_removes_by_task_before_branch_delete (red at cfa37f76)
Fixed: R3 by 44433ea8 — plugins/pd/scripts/test_pd_worktrees.py::test_refused_removal_reads_lock_state_again (red at cfa37f76)
Fixed: R4 by 44433ea8 — plugins/pd/scripts/test_pd_worktrees.py::test_run_in_flight_is_checked_with_nothing_to_remove (red at cfa37f76)
Fixed: R5 by 44433ea8 — plugins/pd/scripts/test_pd_worktrees.py::test_failed_lookup_after_failed_delete_is_exit_2 (red at cfa37f76)
Fixed: R6 by cfa37f76 — plugins/pd/scripts/test_pd_worktrees.py::test_c3_dirty_is_kept now asserts the clean directory and its registration are gone
Fixed: R7 by cfa37f76 — plugins/pd/scripts/test_pd_status_leftovers.py::test_c27_run_in_flight_and_other_branch_items_not_listed now asserts exit 0 and positive controls for both exclusions
Fixed: R8 by cfa37f76 — removal finding, no test: deleted the unused retro option and its branch from make_item()
Closes: review@2026-11-04 14:09+08:00#R2, review@2026-11-04 14:09+08:00#R3, review@2026-11-04 14:09+08:00#R4, review@2026-11-04 14:09+08:00#R5, review@2026-11-04 14:09+08:00#R6, review@2026-11-04 14:09+08:00#R7, review@2026-11-04 14:09+08:00#R8

## 2026-11-04 16:04+08:00 decision
Q: review@2026-11-04 14:09+08:00#R1, a blocker whose fix the fixer rejected because it needs shape.md's pinned `--format=%(refname:short)` (GitSurface, pd-worktrees and pd-status) changed to `%(refname)`: a tag named like a stray branch makes git print `heads/worktree-wf_x`, so the stray vouches for itself and is deleted with its unique commits. Accept the contract change and go back to design, or waive R1?
A (user, verbatim): "Accept, back to design (Recommended)"
Closes: review@2026-11-04 14:09+08:00#R1

## 2026-11-04 16:04+08:00 decision-2
Q: the risk scan's security signal (qa@2026-11-04 14:09+08:00#Q1, qa@2026-11-04 14:09+08:00#Q2), pattern `\btokens?\b`: `plugins/pd/scripts/conftest.py:27: for token in raw.split(b"\0"):` and `plugins/pd/scripts/pd_common.py` worktrees(): `for token in r.stdout.split(b"\0"):`. Set `risk: [security]`, or clear it?
A (user, verbatim): "Clear it (Recommended)"

## 2026-11-04 16:04+08:00 decision-3
Q: QA's open warnings and notes qa@2026-11-04 14:09+08:00#Q3 (`..` and `.` accepted as a work item), #Q4 (C25 can't catch a held branch listed twice), #Q6 (callers run a bare `pd-worktrees`), #Q7 (`--strays --remove --task 1` does nothing, exit 0) and #Q10 (a stray `trace.jsonl` committed by the fixer): fix all in this item, fix Q6 and Q10 only, or backlog them?
A (user, verbatim): "Fix all in this item (Recommended)"

## 2026-11-04 16:04+08:00 phase verify -> design (back)
Reason: R1's accepted fix changes GitSurface's pinned `%(refname:short)` for pd-worktrees and pd-status to `%(refname)`; with it, LeftoverSection's `leftovers(root, art, items)` becomes the code's `leftovers(root, items)` (qa@2026-11-04 14:09+08:00#Q8), and WorktreesCLI's exit-2 list gains an id that is `.`, `..` or holds `/` (#Q3) and `--task` with `--strays` (#Q7).
Invalidates: shape.md ## Design's WorktreesCLI, GitSurface (pd-worktrees, pd-status) and LeftoverSection; plan.md (a task 4 follows); qa@2026-11-04 14:09+08:00 (its commit predates the fix).

## 2026-11-04 16:09+08:00 review design — codex (fallback: no)
Verdict: approved. Commit: 772bf1c2. Scoped re-review of 0351267e..772bf1c2 (shape.md ## Design) against review@2026-11-04 14:09+08:00#R1 and qa@2026-11-04 14:09+08:00#Q3, #Q6, #Q7, #Q8: all five resolved at the contract level, none needing a Requirements change; no new finding in the diff.

## 2026-11-04 16:09+08:00 phase design -> create-plan
Design fix reviewed (review@2026-11-04 16:09+08:00, approved). Next: plan.md's task 4.
