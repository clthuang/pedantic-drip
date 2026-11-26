<!-- Append-only history of 2026-11-26-stage-yolo-decisions-secretary-entry. Entry shapes: plugins/pd/references/log-entries.md. Example:
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."
-->

## 2026-11-26 13:24+08:00 note
Request (verbatim):
> 1) I want to make sure I stay with more powerful model in the main agent and all the text heavy research work should be delegated to some kind fo context gathering agetns. This is to save token cost. How can I achieve this reliably?
> 2) I want to bring back the single entry point (pd:secretary), how can we do that?
> 3) I want to bring back the yolo mode, even if we basically wrap the yolo mode around /goal or /loop or /workflow or something. Although, I personally find the /workflow mode uses a lot of token and normaly being too cautious with each step and ends up building deep with building something usable.
> 
> 1) mostly correct, don't simply logged recommended but add a brief pros and cons and trade-off analysis and implications and premortem report that justifies the decision
> 2) ok
> 3) it's not so much about being able to do tasks inline and instead it is the result of the workflow being too production-considering. So, when it comes to making design decisions, we need to have an idea about if we are at the poc/mvp stage or are we at the productionnization stage which requires different kind of trade off thinking. So, At the poc/mvp stage, we prioritise speed: move fast and break things and iterate. The key is to get to the user, get feedback and iterate to get value delivered fast. Then at the production stage, we want to prioritise architecture robustness, code base consistency, edge case handling, etc. to ensure a robust and easy to maintain code base.

## 2026-11-26 13:24+08:00 note-2
Design input: the stage proposal, agent_sandbox/2026-11-26/pd-stage-yolo-proposal/proposal.md (gitignored; its content moves into shape.md at Contracts). It recommends option C: a project default `stage:` in .claude/pd.local.md, copied into each new work item's frontmatter by pd-new, bound by a pd-review-prompt script and a phase-gate Stage check.

## 2026-11-26 13:24+08:00 decision
Q: where should the mvp/production stage setting live?
A (user, verbatim): "holistically review pd's design and premortem various choices and then make a proposal that is easy to manage, agent binding, and don't go out of sync."

## 2026-11-26 13:24+08:00 decision-2
Q: at the mvp stage, which of triage's standard-depth rules still force standard depth?
A (user, verbatim): "Only risk tags (Recommended)"

## 2026-11-26 13:24+08:00 decision-3
Q: how to take the three changes forward?
A (user, verbatim): "One work item (Recommended)"

## 2026-11-26 13:24+08:00 decision-4
Q: after the proposal, where should the stage setting live?
A (user, verbatim): "Option C (Recommended)"

## 2026-11-26 13:24+08:00 decision-5
Q: fix the two existing sync problems (workflow-results.md restating pinned schemas; suggestion vs note in three reviewer agents) in this work item?
A (user, verbatim): "Include both (Recommended)"

## 2026-11-26 13:30+08:00 decision
Q: is this the right problem? "pd costs too many tokens and over-builds early work: the main session reads raw text itself, every phase stops for you, and every review applies a production-grade bar whatever the work's maturity."
A (user, verbatim): "Yes, that's it (Recommended)"

## 2026-11-26 13:30+08:00 decision-2
Q: which of these mean success: YOLO runs unattended, MVP is visibly lighter, main session stays lean, decisions are auditable?
A (user, verbatim): "YOLO runs unattended, MVP is visibly lighter, Main session stays lean, Decisions are auditable"

## 2026-11-26 13:33+08:00 decision
Q: in YOLO, which user-owned questions (criteria sign-off, calvin's intent questions) still reach the user?
A (user, verbatim): "if YOLO is on, confirm with the user wants it on and after confirmation, YOLO takes priority. Agents can make key decisions on users' behalf with the decision logs that we newly defined"

## 2026-11-26 14:05+08:00 decision
Q: (calvin cycle 1, rows 6, 15, 28) how far should YOLO reach: the whole session (triage, brainstorm, RCA; the gate holds brainstorm and RCA items until promotion; a new session re-confirms), work items only, or skip brainstorm under YOLO?
A (user, verbatim): "Whole session (Recommended)"

## 2026-11-26 14:05+08:00 decision-2
Q: (calvin cycle 1, row 33) which owner-waiting step at the end does a YOLO run take by itself: stop before merge, open the PR without merging, or merge too?
A (user, verbatim): "Open the PR and monitor for any PR comments"

## 2026-11-26 14:05+08:00 decision-3
Q: (calvin cycle 1, row 34) how are the merge-conflict and destructive-operation hard stops enforced: a hook that refuses them while YOLO is on, or a written rule only?
A (user, verbatim): "A hook refuses them (Recommended)"

## 2026-11-26 14:05+08:00 decision-4
Q: (calvin cycle 1, rows 2, 42) how are "MVP is visibly lighter" and "main session stays lean" judged: the owner judges one probe pair and the cost reports, a fixed bar over 3 runs each, or no probes?
A (user, verbatim): "You judge the reports (Recommended)"

## 2026-11-26 14:14+08:00 decision
Q: (calvin cycle 1, row 33) how long does a YOLO run watch the PR it opened: until CI and the automated review settle, until merged or closed, or one pass?
A (user, verbatim): "Until CI + bot review settle (Recommended)"

## 2026-11-26 14:14+08:00 decision-2
Q: (calvin cycle 1, row 29) apply the verify-gate risk check and the decision-record lint in all 20 pd repos, or only to work items created after this change?
A (user, verbatim): "Everywhere (Recommended)"

## 2026-11-26 14:14+08:00 decision-3
Q: (calvin cycle 1, row 17) can a work item that finished at mvp be moved to production?
A (user, verbatim): "No, open a new item (Recommended)"

## 2026-11-26 14:16+08:00 review C1 — calvin-runner (fallback: no)
Verdict: changes requested (20 blocker, 27 minor). Commit: 248eae94. Ledger: agent_sandbox/2026-11-26/2026-11-26-stage-yolo-decisions-secretary-entry/calvin-cycle-1.md.
- C1 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: Goals now say web lookups are refused outright once a budget is set.
- C2 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner (decision-4: "You judge the reports"); conductor added the token rationale to Goals; B44 records figures plus the owner's ruling.
- C3 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the uncounted forms stay a stated non-goal; the owner sees them at sign-off.
- C4 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the goal now says "on the owner's yes".
- C5 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: Goals define a decision made for the owner as every question that would have gone through AskUserQuestion, excluding routine A (conductor) rulings.
- C6 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner ("Whole session"): B51, a new session confirms again.
- C7 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: an mvp blocker is an expectation in shape.md failing on its named input, data loss or exposure, or a security hole.
- C8 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: a harden-later warning is severity warning with category harden-later; no new schema field (category is free text); B49 closes it at finish.
- C9 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the mvp goal now points to the never-relax list.
- C10 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: cites the owner's "too production-considering" (log 13:24 note).
- C11 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: three agents define the word, retro-facilitator reads it.
- C12 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: two copies are forced (workflow scripts read no file, grep of plugins/pd/workflows/*.js finds no fs or shell API; the review call needs markdown); a test binds them. The stage is per-item data, not code read by two runtimes.
- C13 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: cites bake-off.md:120 and :177 for /goal; /loop is a timer; workflows were the owner's cost complaint.
- C14 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: "token budget" is workitem_token_budget throughout; main_read_budget declared unrelated.
- C15 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner ("Whole session"): B56, the gate holds brainstorm and RCA goals until promotion.
- C16 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B17 and B18 start from the owner asking the conductor.
- C17 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner ("No, open a new item"): B46.
- C18 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: "promote" reserved for brainstorm promotion; stage changes say "move".
- C19 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: pointer-only answers are an assumption, now a non-goal.
- C20 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — probe: pd-new's refusal path prints "pd-new: refused: …" and returns 1 (plugins/pd/scripts/pd-new:193-194); B5 pins exit 1.
- C21 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B8 pins the default (config, else production) and the * mark with its footer.
- C22 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B45, the reviewer's JSON echoes stage and the entry copies it; B13 makes verify-change refuse a checklist not from pd-review-prompt.
- C23 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B15 pins "latest" as the last review entry; no entry means no check before Verify.
- C24 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B19 pins the line "Risk: none (<tag>) — <reason>".
- C25 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the section now states its why: the owner's "Only risk tags" ruling has no detector on the express path (verifying/SKILL.md:42).
- C26 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — probe: RISKS = ("security", "migration") (plugins/pd/scripts/pd_common.py:21); B23 says so.
- C27 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B23 reads the stage from the config or secretary's --stage.
- C28 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner ("Whole session"): B24, YOLO is session state from the confirmation on; the first item gets the decision entry.
- C29 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner (row 29: "Everywhere"); census of 20 pd repos found no affected entry or open express item; must-not amended.
- C30 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B29 applies whatever wrote the entry.
- C31 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: Stage belongs in the record because the owner tied design trade-offs to the stage (log 13:24 note, point 3).
- C32 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B30 matches the confirmation and sign-off by their Session: lines.
- C33 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner ("Open the PR and monitor for any PR comments", then "Until CI + bot review settle"): B55.
- C34 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner ("A hook refuses them"): B52, B53, B54.
- C35 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: edge case added; the goal run's Stop gate holds the stop.
- C36 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — probe: docs say subagent hook input carries agent_id and agent_type, and agent_type is also present under --agent (code.claude.com/docs/en/hooks); agent() workflow agents are undocumented. Bake-off.md:128 passed agent_type only for Agent-tool subagents. B34 keys on agent_id; B57 stands the budget down while a workflow runs.
- C37 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: every file under artifacts_root is exempt; must-not reworded.
- C38 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: research answers arrive as the Agent tool's result, not a read, and aren't counted (B36).
- C39 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B38 states the rule (output is file content or search hits).
- C40 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — probe: docs say matching hooks run in parallel (code.claude.com/docs/en/hooks); edge case added.
- C41 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B41 names node plugins/pd/workflows/tests/test-workflows.mjs, a qa_battery command.
- C42 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — owner (decision-4): B43 records figures and the owner's ruling.
- C43 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B47 to B50 added; the Dispatch-line change is diff-only, so Contracts specifies its check.
- C44 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: Out lists the old YOLO features dropped and kept (from git show 35e45296^).
- C45 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: cites bake-off.md:182 (F21).
- C46 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the must-not now says workflow results only record the stage they applied.
- C47 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the old entry point chained phases (secretary orchestrate); B21 is its check.

## 2026-11-26 14:25+08:00 review C2 — calvin-runner (fallback: no)
Verdict: changes requested (cycle 1: 45 resolved, 2 reopened; new: 18 blocker, 12 minor). Commit: 31ef972c. Ledger: agent_sandbox/2026-11-26/2026-11-26-stage-yolo-decisions-secretary-entry/calvin-cycle-2.md. All rows answered by the conductor; the owner sees the result at sign-off.
- C22 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the prompt's first line carries the stage paragraph's hash, the reviewer echoes it (B45), and B15 compares it with the current hash, so a prompt without pd-review-prompt's paragraph fails the gate.
- C42 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B61, finish needs both rulings, and a negative one names the owner's next step.
- C48 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B24, decisions made before the first item exists go to that item's log after the confirmation entry.
- C49 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B24, every item a YOLO session first writes to gets its own confirmation entry, the promoted work item included.
- C50 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B51, the new session's confirmation entry goes to the existing item's log.
- C51 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B60, pd-yolo on|off|status keeps the session's state; the owner turns YOLO off by asking.
- C52 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B55, a yes runs pd-yolo off and finish's merge and cleanup run as today; a no clears the goal line and leaves the PR open.
- C53 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B55, settled means gh pr checks shows no pending check; up to 3 fix cycles; no remote or no gh skips the PR.
- C54 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B52's list is the whole destructive set; Out names single-file rm, find -delete and scripts.
- C55 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B53, no allow-once state; the owner runs an approved command with "! <command>".
- C56 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B52 refuses gh pr merge and pushes to the base branch.
- C57 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — probe: implement-tasks.js:54 has a fix agent run "git worktree remove --force" on its task worktree, and merger.md:27 says the merger aborts on conflict and never resolves. B52 applies to every caller but exempts .claude/worktrees/; B54 can't block the merger.
- C58 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B40, the destructive and merge-conflict hook fails closed on a matching command; the read and AskUserQuestion hooks fail open.
- C59 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B59 added.
- C60 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B47 now checks a Deferred: line (pd-lint warns without one); which cases stay is judged at sign-off.
- C61 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B44 counts cache reads (the re-sends), and falls back to the transcripts' usage fields if the report can't split main from subagent transcripts.
- C62 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B16 skips review entries without a Stage: line (calvin cycles, older entries); B58 makes pd-lint require Stage: on review-call entries.
- C63 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B42 pins exact patterns.
- C64 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B17, B18, B46 and B55 are marked (live probe), checked in a headless claude -p run at Verify.
- C65 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the harden-later issue line reads "warning harden-later" (Goals, B49).
- C66 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B49, one backlog line per work item naming each issue as review@<timestamp>#<id>.
- C67 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B19 matches "Risk: none (<tag>)" followed by any reason.
- C68 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — probe: workflow-transitions/SKILL.md:12 defines "run in flight: <run-name> session <session id>"; B57 cites it.
- C69 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B38, the list is the rule.
- C70 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the prefix only lets a question through and unlocks nothing (B53); edge case added.
- C71 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B50 separates the script from the command.
- C72 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the must-not separates today's census from "from now on".
- C73 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: the echo shows the reviewer's prompt carried the stage paragraph, for the conductor's own review calls too.
- C74 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B17, no backward move while still in specify.
- C75 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: Goals name WebFetch and WebSearch.
- C76 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: B54, the owner resolves or turns YOLO off.
- C77 minor docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md — conductor: citations now use entry references (decision-2@2026-11-26 14:05+08:00, decision@2026-11-26 14:14+08:00).

## 2026-11-26 14:32+08:00 review C3 — calvin-runner (fallback: no)
Verdict: changes requested (cycle 2: 30 resolved, 2 reopened; new: 25 blocker, 10 minor). Commit: f2d62b4c. Ledger: agent_sandbox/2026-11-26/2026-11-26-stage-yolo-decisions-secretary-entry/calvin-cycle-3.md. Not answered: the loop reached its cap; see the capped entry.

## 2026-11-26 14:32+08:00 capped specify
Deferred:
- Mechanism rows, for Contracts (they ask how, not what): C22, C78, C79, C83, C84, C85, C91, C92, C93, C94, C95, C97, C98, C99, C101, C102, C103, C104, C105, C108, C109, C110, C111, C112.
- Behaviour rows, for the owner's ruling: C53, C80, C81, C82, C86, C88, C89, C90, C100, C106, C107.
Follow-ups: none
Decisions: none
Assumptions:
- A1: a command the owner runs with "! <command>" reaches no PreToolUse hook (C87); to probe at Contracts.
- A2: the automated review shows in gh pr checks as a check; verified in this repo, where PR #35 lists "review pass" beside "validate pass" (gh pr checks 35, 2026-11-26).
Closes: none

## 2026-11-26 14:37+08:00 decision
Q: calvin hit its cap with 37 questions open: apply the behaviour defaults, move the mechanism questions to Contracts and sign off; split into three work items; or one more calvin pass?
A (user, verbatim): "Defaults, then sign off (Recommended)"
answers: capped@2026-11-26 14:32+08:00

## 2026-11-26 14:38+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Signed off"

## 2026-11-26 14:38+08:00 phase specify -> design

## 2026-11-26 15:11+08:00 review M1 — codex (fallback: no)
Verdict: changes requested. Commit: 579648df.
- R1 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:557 — production to mvp after Contracts can't commit: pd-lint re-runs the design and create-plan gates at implement (pd-lint:363-380), whose stage check then rejects the earlier review.
- R2 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:355 — the fixer runs in its own worktree (implement-tasks.js:69-70), so rev-parse --show-toplevel puts .claude/worktrees/ under it and the previous attempt's removal is refused.
- R3 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:371 — WebFetch and WebSearch are refused while a workflow runs; B57 says the budget refuses nothing then.
- R4 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:341 — the crash fallback's raw-word test passes git p'ush' -f, a quoted form SimpleCommands reads.
- R5 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:338 — the conflict probe ignores --git-dir and --work-tree, so it can inspect another repository than the guarded command.
- R6 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:522 — open blockers can be closed by qa, review or capped entries without the owner (pd_common.py:366-391), pass when never written, and don't check the adverse-ruling next step (B61).
- R7 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:550 — pd-yolo status and off are called without --session, which YoloCLI requires.
- R8 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:435 — comparing key sets misses a type, requiredness or enum change (B41).
- R9 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:446 — workflow-results.md's verify-change result block (workflow-results.md:48-57) gains stage too, and test-workflows.mjs:93-94 compares it.
- R10 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:713 — claude -p can't host AskUserQuestion or a "!" command, so the live probes need an interactive harness, saved evidence and their network use named.
- R11 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:698 — "Fakes: none" omits test-workflows.mjs's stubs of agent, parallel, pipeline, budget, log and phase (test-workflows.mjs:26-36).
- R12 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:749 — the suggestion-to-note rename has no surface inventory and misses review-ds-code.md:153 and review-ds-analysis.md:165.
- R13 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:339 — the git and gh outputs parsed lack recorded probes of their variants.
- R14 warning docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:673 — the census missed implementing/SKILL.md:27 and :33 and abandon-workitem.md:12.

## 2026-11-26 15:23+08:00 review M2 — codex (fallback: no)
Verdict: changes requested (scoped: 12 of 14 resolved; R6 and R13 open; 3 new, kept by pd-review-filter --range 579648df..415fa592). Commit: 415fa592.
- R6 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:545 — still open: any non-empty Next: passes, so a "missed" ruling with Next: none closes B61.
- R13 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:771 — still open: gh pending and failing outputs unprobed; the symbolic-ref probes lack the same-named tag, slash name and chain cases.
- R15 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:345 — the crash fallback misses a command split by a backslash-newline (git pu\<newline>sh -f).
- R16 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:363 — under --separate-git-dir the common dir's parent isn't the checkout, so rm -rf <store>/agent_sandbox/x would be allowed.
- R17 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:537 — a stage changed at finish skips the stage check, so the item can close without a review applying the new stage (B18).

## 2026-11-26 15:32+08:00 review M3 — codex (fallback: no)
Verdict: changes requested (scoped: R6, R15 and R17 resolved; R13 and R16 open; 1 new). Commit: 5d36aa0a.
- R13 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:778 — still open: the pending-check output wasn't probed, only read from help text.
- R16 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:363 — still open: a separate git dir named .git elsewhere (/store/.git) passes the basename test, so /store counts as the checkout.
- R18 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/shape.md:604 — at the Bash tool's timeout Claude Code moves the command to the background instead of stopping it, so the loop would start a second watcher.

## 2026-11-26 15:32+08:00 capped design
Deferred:
- R13: now probed (gh 2.103.3, 2026-11-26): ductura/Institution_server PR 826 with 9 pending checks, gh pr checks exits 8 and --json name,bucket gives pending=9. Proposed: record it in the probes table.
- R16: reproduced the class with --separate-git-dir (scratch repo, git 2.54.0). Proposed: drop the common-dir rule; a git worktree remove is exempt when git worktree list --porcelain shows that path on a pd/<id>/task-<n> branch (pd_common.worktrees, TASK_BRANCH); an rm -r operand is allowed only inside the command's own toplevel's agent_sandbox/.
- R18: reproduced: gh pr checks --watch on that pending PR was moved to the background at 120 s, and perl alarm 15 didn't stop gh. Proposed: a new pd-pr-checks <pr> script polls gh pr checks --json name,bucket every 30 s for at most 540 s, prints the buckets and exits 0 (all passed or skipped), 1 (a failure), 3 (no checks), 8 (still pending) or 2 (gh failed); the conductor runs it with the Bash tool's timeout at 600000 ms, at most 7 times.
Follow-ups: none
Decisions: none
Assumptions:
- A3: Claude Code keeps moving a foreground Bash call that outlives its timeout to the background (seen 2026-11-26 in this session).
Closes: none

## 2026-11-26 15:43+08:00 decision
Q: the Contracts review hit its cap with R13, R16 and R18 open, each reproduced with a fix ready: apply them and go to Plan, apply them and run a fourth review, or defer the PR wait?
A (user, verbatim): "Apply fixes, go to Plan (Recommended)"
answers: capped@2026-11-26 15:32+08:00

## 2026-11-26 15:43+08:00 phase design -> create-plan

## 2026-11-26 15:44+08:00 decision
Q: which design review blockers are resolved?
A (conductor): the scoped re-reviews marked M1's R1-R5 and R7-R12 resolved (review M2), M1's R6 and M2's R6, R15 and R17 resolved (review M3); M1's R13 and M2's R13 and R16, carried into M3's R13 and R16, and M3's R18 were fixed in commit 007bdfdb as the owner ruled (decision@2026-11-26 15:43+08:00).
Closes: review@2026-11-26 15:11+08:00#R1, review@2026-11-26 15:11+08:00#R2, review@2026-11-26 15:11+08:00#R3, review@2026-11-26 15:11+08:00#R4, review@2026-11-26 15:11+08:00#R5, review@2026-11-26 15:11+08:00#R6, review@2026-11-26 15:11+08:00#R7, review@2026-11-26 15:11+08:00#R8, review@2026-11-26 15:11+08:00#R9, review@2026-11-26 15:11+08:00#R10, review@2026-11-26 15:11+08:00#R11, review@2026-11-26 15:11+08:00#R12, review@2026-11-26 15:11+08:00#R13, review@2026-11-26 15:23+08:00#R6, review@2026-11-26 15:23+08:00#R13, review@2026-11-26 15:23+08:00#R15, review@2026-11-26 15:23+08:00#R16, review@2026-11-26 15:23+08:00#R17, review@2026-11-26 15:32+08:00#R13, review@2026-11-26 15:32+08:00#R16, review@2026-11-26 15:32+08:00#R18

## 2026-11-26 15:55+08:00 decision
Q: the live checks at Verify can't run in headless claude -p (no answered questions, no ! commands), while the signed-off criteria say headless: switch to an interactive session the owner drives, or run headless where possible?
A (user, verbatim): "Headless where possible"

## 2026-11-26 15:55+08:00 decision-2
Q: the diff will match pd's security risk pattern, and the hooks are safety controls: tag risk: security, or record Risk: none (security)?
A (user, verbatim): "Tag risk: security (Recommended)"

## 2026-11-26 16:23+08:00 review P1 — codex (fallback: no)
Verdict: changes requested (13 blockers). Commit: 6e7f7348. Every claim checked at file:line before fixing (validate.sh:738 runs check-doc-drift.sh; pd-lint:549-552 resolves the item from the branch; finishing-branch/SKILL.md:20 runs the finish gate at step 4).
- R1 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:272 — Task 11 can't pass validate.sh at the Wave 3 base: check-doc-drift.sh:58-61 rejects the unregistered wave-2 hooks, registered only by Task 12 in the same parallel wave.
- R2 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:73 — Task 1's waiver case is vacuous: HEAD~1..HEAD after the waiver commit no longer holds the api.py change, and pd_repo leaves main checked out, so branch_workitem finds no item.
- R3 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:255 — no case proves the YOLO path starts the goal run, or that --yolo on an existing item writes the new session's goal line (B51).
- R4 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:265 — no case covers B55's review-comment handling, with passing checks, or the hard stop when comments remain.
- R5 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:147 — B54's rebase --continue and cherry-pick --continue, and the guard reading the selected repo's index (--git-dir, --work-tree), are unproved.
- R6 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:148 — B40's crash and unreadable-state paths are never injected.
- R7 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:213 — the stage check at finish, and a newer unstaged review after a mismatching staged one, are untested.
- R8 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:159 — the read budget's agent_type-without-agent_id, a non-default artifacts_root and the full READ_WORDS list are unproved.
- R9 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:210 — B29's case never removes Session: or Stage:, so a checker requiring four labels passes.
- R10 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:219 — B49's case holds one issue, not several across entries with suffixed references.
- R11 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:235 — no case asserts the mvp paragraph's blocker rule itself.
- R12 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:237 — B45's reviewer half has neither a test nor a probe in plan.md.
- R13 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:268 — the harden-later backlog line was placed before step 6, after step 4's finish gate that requires it.

## 2026-11-26 16:23+08:00 review-2 P1 — calvin-runner (fallback: no)
Verdict: changes requested (6 blocker, 24 warning, 35 note). Commit: 6e7f7348. Ledger: agent_sandbox/2026-11-26/2026-11-26-stage-yolo-decisions-secretary-entry/calvin-plan-cycle-1.md. Each row answered by the conductor (wording, consistency or mechanism; no row asked for the owner's intent).
- Q8 blocker — conductor: the suite rule is now the grep that finds suites naming an edited file (run 2026-11-26); each task's last case lists its suites; Tasks 1, 4, 7, 8, 9 and 12 gained the missing ones.
- Q25 blocker — conductor: same as review P1 R2; the case uses main..HEAD on the work item's branch.
- Q31 blocker — conductor: no new interface; C9 relies on the sleep never running past --for (PrChecksCLI), and C11 waits about 30 seconds.
- Q55 blocker — conductor: the copied block is the lines between the json fences, fences left out.
- Q58 blocker — conductor: secretary.md starts the goal run per workflow-transitions' "Goal runs", whose ${CLAUDE_SESSION_ID} writes the line; ConductorProse says so.
- Q59 blocker — conductor: create-workitem.md joins Task 11 for its argument-hint; $ARGUMENTS already reaches pd-new (create-workitem.md:10).
- Q3, Q4, Q5, Q7, Q9, Q12, Q14, Q17, Q19, Q22, Q23, Q34, Q35, Q38, Q43, Q46, Q49, Q51, Q61, Q62, Q63 warning — conductor: answered in plan.md's shared terms, probes or the named cases (README stage line written by the case, run_hook env, stderr scope, pending exit, case independence, "fails until", the installed plugin disabled for probes, B45 and B55 evidence, the guard's stderr labels, B54's commands, goal line text, the 13 files named, finish's stage check, B55's comments and wait loop).
- Q26, Q33, Q57 warning — conductor: checked, no change: WRAPPERS gives sudo's -u an argument (commit_target.py:26); every fix-text field reads "suggestion": "How to fix it"; test-workflows.mjs names each check it runs.
- Notes (35) — read; none changes what an executor builds.

## 2026-11-26 16:30+08:00 review P2 — codex (fallback: no)
Verdict: changes requested (scoped: R1-R13 resolved; 1 new blocker, 1 new warning). Commit: 0d871787. New findings filtered by pd-review-filter --range 6e7f7348..0d871787 (both kept). N1 checked: merger.md:28 re-runs every landed task's proof after each merge, so it also hit Task 4's validate.sh, not only Tasks 7 and 8.
- N1 blocker docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:189 — Tasks 7 and 8 newly run validate.sh and check-doc-drift.sh, which fail once Tasks 5 and 6 land hooks that only Task 12 registers, since the merger re-runs every landed proof.
- N2 warning docs/dev_artifacts/workitems/2026-11-26-stage-yolo-decisions-secretary-entry/plan.md:77 — Task 1's suites omit the self-tests of pd-adopt, pd-init, pd-proof, pd-review-filter and pd-html.py, which import pd_common.
Closes: review@2026-11-26 16:23+08:00#R1, review@2026-11-26 16:23+08:00#R2, review@2026-11-26 16:23+08:00#R3, review@2026-11-26 16:23+08:00#R4, review@2026-11-26 16:23+08:00#R5, review@2026-11-26 16:23+08:00#R6, review@2026-11-26 16:23+08:00#R7, review@2026-11-26 16:23+08:00#R8, review@2026-11-26 16:23+08:00#R9, review@2026-11-26 16:23+08:00#R10, review@2026-11-26 16:23+08:00#R11, review@2026-11-26 16:23+08:00#R12, review@2026-11-26 16:23+08:00#R13

## 2026-11-26 16:35+08:00 review P3 — codex (fallback: no)
Verdict: approved (scoped: N1 and N2 resolved, no new finding). Commit: 5ae4bdc3. Merge order checked against implement-tasks.js:95-101: tasks 1-10, then 12, then 11.
Closes: review@2026-11-26 16:30+08:00#N1, review@2026-11-26 16:30+08:00#N2

## 2026-11-26 16:35+08:00 phase create-plan -> implement
