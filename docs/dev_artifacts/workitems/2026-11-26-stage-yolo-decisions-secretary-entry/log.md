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
