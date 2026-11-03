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
