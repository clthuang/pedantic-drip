# Calvin's second report applied to the thin-pd plan (2026-10-14)

Source: `agent_sandbox/2026-10-14/calvin-thin-pd/adjudication-2.md`.

**Counts:**
- **86 R or R (user) findings applied,** listed below.
- **No plan change for the R0 rows:** #31, #42, #67.
- **D17 added to §15** after D16; the Status line, the annex list and §16 step 1 updated.
- **§16 renumbered:** new step 2 (commit the plan), new step 3 (inventory, then delete); old steps 2-6 became 4-8. Every "§16 step N" and "steps 2 and 3" reference was swept.

| # | Verdict | Plan section(s) changed |
|---|---|---|
| 1 | R | §A2 table rows 0 and 1; §A2 entry-depth list (RCA line points to row 1) |
| 2 | R | §A2 row 2; §A3 Rule 1 (new `calvin-runner` bullet; calvin out of the reviewers list); §A6 agents (21 kept plus 2 new); §12 plugin ships and `/pd:init`; §16 step 5 |
| 3 | R | §A5 stops list, split into hard stops and decisions; print-mode bullet points back to it |
| 4 | R | §A2 row 4 gate (points to §9); Part B §9 Plans (`uses:` rule and the base at `create-plan`) |
| 5 | R | §A2 row 5; §A4 merger check step 1; §A4 lazy-stub bullet |
| 6 | R | §A2 row 6 gate; Part B §6 (`qa` entry records its commit); §12 `qa_battery` |
| 7 | R | §A4 (new security-review bullet); §A5 cap 2 agent list |
| 8 | R | §A2 budgets (exception bullet); §A2 "What a move invalidates" |
| 9 | R | §A2 risk tags (tag set at Verify) |
| 10 | R | §12 `/pd:init` intro; §12 field list (new defaults bullet) |
| 11 | R | §A2 row 4; §A3 (every task in its own worktree); §A4 `implement-tasks` row; §A8.3 S5; canonical diagram T3 node |
| 12 | R | §A4 `implement-tasks` row; Part B §10 task worktrees |
| 13 | R | §A5 "Who writes the line" |
| 14 | R | §A5 (new "Reaching the target" bullet) |
| 15 | R | §A5 "When it acts"; §A5 cap 3 "Per feature" |
| 16 | R | §A6 (`updating-docs` kept; commands line; inventory rule); §12 plugin ships |
| 17 | R | §A7 intro (probe bullet) |
| 18 | R (user) | §A7 item 6; §16 judgement; §A5 "Why a goal spends more"; D17 |
| 19 | R | §A7 item 6; §12 budget defaults; §16 step 6 |
| 20 | R | Part B §9 phase artifacts |
| 21 | R | §12 adopt step 2 |
| 22 | R (user) | §A6 inventory; §A7 intro ("deletions wait" removed); §16 new step 3, old step 4's deletions removed, judgement; D17 |
| 23 | R | Provenance annex list; D16 (points at the annex `calvin-applied.md`) |
| 24 | R | Provenance line; §A1 essay line; §16 new step 2 and step 7 |
| 25 | R | Part B §3 tree and new "A plan's annex" bullet |
| 26 | R | §A8 "Where each lands"; §A8.2 table; §A8.3 S1 and S4; §A8.4 tables and planning bullet; Part B §9; D10; D12 |
| 27 | R | §A1 gates line; §A8.1 first bullet; §A8.3 S6 "Why" |
| 28 | R | §A2 diagram bullets |
| 29 | R | §A2 row 0; Part B §5 frontmatter `mode` comment, `mode` and `risk` rows |
| 30 | R | Part B §7.1 creating a planned item; D16 author's call |
| 32 | R | §A2 row 4; §A8.3 S5 |
| 33 | R | §A2 small feature bullet |
| 34 | R | §A2 Criteria cycle |
| 35 | R | §A2 Criteria cycle |
| 36 | R | §A2 judgement finding |
| 37 | R | §A4 result schema; §A2 flake line |
| 38 | R | §A2 rejected finding |
| 39 | R | §A2 `capped` bullet; Part B §6 decision entry; Part B §11 |
| 40 | R | §A2 assumptions list |
| 41 | R | §A2 escalation bullet; §A3 executors line |
| 43 | R | §A2 small feature (Triage's own entry; overrun is a `note`) |
| 44 | R | §A2 always-standard list; canonical diagram Triage node |
| 45 | R | §A2 "What a move invalidates" and re-confirming rule |
| 46 | R | §A3 (`calvin-runner`, QA and merger bullets); §A6 merger; Part B §9 agent write hook; §16 step 5 D16 line |
| 47 | R | §A3 quality bars; §A4 checklist bullet (now points to §A3) |
| 48 | R | §A5 cap 4 |
| 49 | R | §A3, §A5 and §A8.4: seven elided sources expanded to full URLs |
| 50 | R | §A4 result schema (every result); §A5 cap 1 |
| 51 | R | §A4 result schema; `rca-fanout` row |
| 52 | R | §A4 `rca-fanout` row; §A8.3 S5; canonical diagram Clarify node |
| 53 | R | Part B §8 rule 3 |
| 54 | R | §A4 green-only line |
| 55 | R | §A4 wrong test case |
| 56 | R | §A4 review call |
| 57 | R | §A4 review call ("Before code, a pass with no blocker…") |
| 58 | R | §A5 token cap bullet; §12 `budget_increment` |
| 59 | R | §A5 interactive bullet; Part B §8 rule 3; §A9 table (same qualifier) |
| 60 | R | §A5 cap 1 |
| 61 | R | §A8.3 S5; §A5 cap 2 |
| 62 | R | §A6 hooks line |
| 63 | R | §A4 result schema and `run` entry line; §A7 item 6 |
| 64 | R | §A8 "Where each lands" |
| 65 | R | D16 author's calls; §A8.4 intro |
| 66 | R | Part B §1 "Comprehensive" |
| 68 | R | Part B §4.1 (new backlog bullet); §7 ids; §9 backlog check |
| 69 | R | Part B §4.1 collisions; §A4 merger check step 4; §9 ids |
| 70 | R | Part B §4.1 short references; §4.2 and §7.1 (`/pd:finish-feature`) |
| 71 | R | Part B §6 heading format and examples; §6 phase, decision and blocker references; §11; §A2 `capped` bullet |
| 72 | R | Part B §6 (converted entry); §11; §12 adopt step 4 |
| 73 | R | Part B §6 (new same-minute bullet) |
| 74 | R | Part B §6 metrics (stops moved to "Derived, never written"). §A2 had no restatement |
| 75 | R | Part B §6 figures bullet |
| 76 | R | Part B §6 figures bullet |
| 77 | R | Part B §10 `agent_sandbox/` row |
| 78 | R | Part B §9 `issue:` |
| 79 | R | Part B §9 cost overrun; §A5 cap 3 state file |
| 80 | R | Part B §9 Plans |
| 81 | R | §A2 row 3; Part B §9 test isolation; §12 templates |
| 82 | R | Part B §10 task branches |
| 83 | R | §16 step 4 |
| 84 | R | §12 adopt step 0; retired-fields line |
| 85 | R | §12 detection |
| 86 | R | §12 adopt step 0 |
| 87 | R | §12 adopt step 0; D5 export line |
| 88 | R | §16 step 6 |
| 89 | R | Part B §9 (new cited-commits check) |

## Flags: answers I couldn't apply cleanly

1. **#22 and D17 cite "D15's deferral of deletions",** but the plan records that deferral under D14 ("Defer compare + deletions"), and old §16 step 4 said "D14: they wait". D17 says it supersedes **D14's** deferral. Please confirm.
2. **#22 against §16 step 8.** Step 8 still retires the registry, the MCP servers, the Kanban UI and the YOLO hooks only after all four projects adopt.
   - **The registry, MCP and UI code:** these are not skills, commands, agents or hooks, so step 3's inventory doesn't list them, and step 8 stands for them.
   - **The YOLO hooks and `/pd:yolo`:** these are hooks and a command the new design doesn't use (`yolo-stop.sh` is only the port's source), so D17's rule would delete them at step 3.
   - **What I did:** I left step 8 unchanged. The author should decide whether D17 pulls any of this forward.
3. **#22: S6's staged prune.** The prune of CLAUDE.md and the skills was part of the old post-bake-off "deletions". It edits content rather than deleting components, so I kept it after the bake-off (§16 step 6), minus the "old path" reason. Please confirm, or move it into step 3.
4. **#3: "a small overrun" is listed as a decision,** but §A2 (and #43) has the conductor record it as a `note` without asking anyone. I applied it as written; nothing says what would be asked.
5. **#13: "the conductor clears the `goal:` line only when the user says stop".** I kept the existing clearing in the turn where `pd-status` shows the target reached. Dropping it would leave a stale `goal:` line on a done feature. Please confirm.
6. **#43: `phase triage -> <first stage>`.** `triage` isn't in the `phase` vocabulary (§5). That vocabulary governs the frontmatter field, so lint won't trip, but a `phase` entry's from and to have no stated vocabulary. Also, work entering at Clarify has no feature yet, so Triage's entry goes in the brainstorm or rca item's `## Log`.
7. **#73: where the `-2` goes.** I put the suffix on the kind (`review-2`), so references read `review-2@<date> <time>`; that placement is my call. A third entry in the same minute isn't covered.
8. **#27 reaches beyond the plan.** The essay §14 ("the written rule against it prevented none") and both HTML decks restate the claim. The answer cites only plan lines, so I left them unchanged.
9. **#79 with #66.** The cost-overrun trigger reads the original budget from the gate's state file under `~/.claude/pd/gate/`, which can be lost, and `pd-lint` re-runs that check at every later commit. Nothing in git records the original budget. Consider having `metrics` copy it.
10. **#84: `sop: 1` as adopt's first change.** It arms `pd-lint`'s forbidden-file check (§9) while `.meta.json` and the review files still exist, until steps 2 and 4 remove them. Adopt's own commits may then be blocked by the commit hook. Applied as written; the author may want `sop: 1` written last.
11. **#85: a missing file and `docs/features/` together.** Both of the answer's rules apply. I kept the plan's earlier outcome ("run /pd:adopt"), and offer `/pd:init` only otherwise.
12. **#46: the hook has nothing to key on.** It limits `calvin-runner` to "its ledger path", but no section names that path.
13. **#11: what `[parallel-safe]` now means.** Every task gets a worktree, so "big enough to pay for a worktree" no longer distinguishes it. I wrote "big enough for running in parallel to pay" (§A2 row 4, S5); the wording is mine.
14. **#49:** the URLs use the prefix the answer gives (`https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/…`). I did not fetch them. Other sources in the plan omit the scheme, so these now differ in style.
15. **#23:** this change log isn't in the annex list. I wasn't permitted to copy it there.

## Notes (applied, no conflict)

- **#18, "D16's text":** D16's own bullets carry no 2× figure. The comparison was in §16's judgement under D16's heading, and it is gone from there.
- **#5:** the essay §7 and `workflow-principles.mmd` mention raising stubs only for a new module. Neither forbids lines added to existing modules, so both are unchanged.
- **#26:** every essay citation now uses "§N, *title*", including the parenthetical forms and the §A8.4 "Principle it keeps" column.
- **Diagram:** `docs/workflow-canonical.mmd` was changed for #11 (T3 node), #44 (Triage node) and #52 (Clarify node), then re-rendered to PNG and checked: nothing overlaps or clips. As in the first pass, the escalation label sits beside the sequential-task edge, but it reads fine. `workflow-principles.mmd` is unchanged, so it wasn't re-rendered.
- **The essay** is unchanged, and `awk 'length>100'` prints nothing.
