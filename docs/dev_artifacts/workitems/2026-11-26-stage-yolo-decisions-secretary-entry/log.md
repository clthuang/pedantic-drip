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
