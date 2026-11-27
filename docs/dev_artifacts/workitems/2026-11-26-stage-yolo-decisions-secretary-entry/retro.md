# Retro: Stage, YOLO decisions, secretary entry point, main-session read budget

## Trigger

Only the capped trigger fired (finish-gate.txt: "retro.md missing: log.md records a retro trigger (capped)"). The log holds four `capped` entries and one backward move:

- **capped@2026-11-26 14:32+08:00 (specify):** calvin cycle 3 at the cap. The owner chose "Defaults, then sign off" at decision@14:37.
- **capped@2026-11-26 15:32+08:00 (design):** review M3 left R13, R16 and R18 open. The owner chose "Apply fixes, go to Plan" at decision@15:43.
- **capped@2026-11-26 19:30+08:00 (verify):** qa@19:30#Q10 was still open after three fix cycles. The owner chose "One more cycle, Q10 only" at decision@19:39.
- **capped@2026-11-26 20:02+08:00 (verify):** qa@20:02#Q11 and #Q12 were found after the extra cycle. The conductor sent them to the backlog, as decision@19:39 had ruled (decision@20:02).
- **phase@2026-11-26 22:19+08:00, finish -> verify (back):** the security review's S1-S3 (review@22:19). This move is not a trigger by itself.

Both verify caps and the backward move came from the YOLO guard's Bash parsing (`commit_target.py`, `pd-yolo-guard.sh`). The specify and design caps came from other parts of the item.

## Aims

From the request (note@13:24) and the problem statement the owner accepted (decision@13:30): "pd costs too many tokens and over-builds early work."

- **Four parts, in one work item (decision-3@13:24):**
  - **Stage:** an mvp/production `stage:`, set as a project default and copied into each item (Option C, decision-4@13:24).
  - **YOLO:** the owner confirms it per session; agents decide with decision records; the merge stays the owner's; a hook refuses destructive commands and merge conflicts (decision-3@14:05).
  - **Entry point:** `/pd:secretary` comes back, with a goal-run offer.
  - **Read budget:** a cap on the main session's reads.
- **Success criteria (decision-2@13:30):** "YOLO runs unattended, MVP is visibly lighter, Main session stays lean, Decisions are auditable".
- **Size:** shape.md holds 60 expectations (`^B\d+:` grep count is 60, which matches the 53336fa8 subject). Risk is tagged `security` (decision-2@15:55).

## Outcomes

**Delivered**
- **Tasks:** all 12 merged with proof passing (run@17:56). Task 12 needed 1 fix cycle; the other 11 needed none. 25 agents, 281,242 tokens.
- **Branch:** 101 commits (git-log.txt) and 66 files changed, +5,066/-127 (git-diff-stat.txt).
- **Tests:** at 1e6a06fc all nine battery commands pass, and pytest gives 390 passed (qa@22:47).

**Stage by stage**

| Stage | Window | Passes | Blockers | Notes |
|---|---|---|---|---|
| Criteria | 13:24-14:38 | 3 calvin cycles (review C1@14:16, C2@14:25, C3@14:32) | 20, 18, 25 (plus 27, 12 and 10 minor) | capped@14:32 |
| Contracts | 14:38-15:43 | 3 Codex passes (M1@15:11, M2@15:23, M3@15:32) | 13, 5, 3 issue lines, which are 17 distinct findings; M1 also had 1 warning | capped@15:32; decision@15:44 closes all 21 lines |
| Plan | 15:43-16:35 | Codex P1@16:23, calvin review-2 P1@16:23, Codex P2@16:30, Codex P3@16:35 | 13; calvin 6 (plus 24 warnings and 35 notes); 1 (plus 1 warning); 0, approved | no cap |
| Implement | 16:35-17:57 | run@17:56 | none | three flake notes at 17:56: the first post-merge JUnit report was empty for tasks 1, 3 and 8 |
| Verify | 17:57-21:43 | run@19:30 (8 agents, 203,404 tokens, 3 cycles); run@20:02 resumed (cycle 4, "Agents: 10", 74,607 tokens); qa@19:30, qa@20:02 | review@19:30: 8 blockers and 1 warning; QA blockers qa@19:30#Q10, qa@20:02#Q11 and #Q12 | capped@19:30, capped@20:02 |
| Finish | 21:43-22:19 | qa@21:51 (battery re-run after CHANGELOG); review@22:19 (security-reviewer) | 3 (S1-S3), plus 2 warnings and 2 notes | back to verify |
| Verify (seeded) | 22:19-22:47 | run@22:47 (4 agents, 86,403 tokens, 2 cycles); qa@22:47 | fixed S1-S3 and the prior pass's Q1 and Q2; qa@22:47#Q3-#Q10 went to the backlog | phase@22:47 back to finish |

**Totals**
- **Review entries:** 12. Calvin ran 4 (69 blocker lines: 20+18+25+6), Codex 7 (43 blocker lines: 13+5+3+13+1+0+8) and security-reviewer 1 (3 blockers).
- **QA entries:** 4 (qa@19:30, @20:02, @21:51, @22:47), each with all nine battery commands passing. The QA passes inside the runs are named only by commit, so they are not counted here.
- **Fix cycles at Verify:** 6 up to qa@22:47 (3 + 1 + 2), 10 in all with the two later seeded runs (+1 at run@2026-11-27 09:14, +3 at run@2026-11-27 09:50). run@20:02's "Cycles: 4" includes run@19:30's three.
- **Workflow tokens:** 645,656 across the first four runs; 773,323 across all six (+31,651 at run@2026-11-27 09:14, +96,016 at run@2026-11-27 09:50). Whole item: 16,434,779 tokens from the Stop gate (metrics@2026-11-27 09:51), no budget set.
- **Agents:** run@20:02's "Agents: 10" may include run@19:30's 8, since decision@19:39's plan says the review and cycles 1-3 "replay from cache". The entry doesn't say, so no agent total is given.
- **Live probes:** cost $7.33 (qa@20:02).

**Parser and guard work compared with the rest (Verify and Finish)**

| Pass | Parser and guard | Everything else |
|---|---|---|
| review@19:30 | R1 (`commit_target.py:368`), R2 (`pd-yolo-guard.sh:115`) | R3-R8: phase-gate, Stop gate (2), read budget, pd-pr-checks, a test |
| QA findings in run@19:30 (from qa@19:30) | Q1, Q6, Q7, Q9, Q10 | Q3, Q4, Q5, Q8. Q2 has no line in the entry |
| run@19:30's fix commits | 12 of 23 | 11 |
| run@20:02 (cycle 4) | all 4 commits; new findings qa@20:02#Q11, #Q12, #Q13 | none |
| qa@21:51 | none | CHANGELOG re-run only |
| review@22:19 | S1-S5 and S7 (all 3 blockers) | S6 (phase-gate) |
| run@22:47 | all 5 commits; qa@22:47#Q3-#Q10 | none |

- **Fix cycles:** read from three commit clusters in run@19:30 (18:22-18:31, 18:52-18:58, 19:15-19:20). This is inferred from timing, not logged.
  - Cycle 1 was the only mixed cycle: 4 guard commits and 11 others.
  - The other five cycles touched only `commit_target.py`, `pd-yolo-guard.sh` and their tests.
- **Fix commits:** 21 of the 32 at Verify (66%) went to the parser and guard, including every one after cycle 1.
- **Tokens:** the two parser-only runs (run@20:02 and run@22:47) used 161,010 tokens, 44% of the 364,414 Verify workflow tokens.
- **Diff share:** those four files are 800 of about 3,397 changed lines outside the work item's artifacts, about 24%.
- **Before code:** guard findings were already there. At Contracts they were M1#R2, #R4, #R5 and M2#R15, #R16, 5 of 17 distinct findings. M1#R4 (`git p'ush' -f`) and M2#R15 (a backslash-newline) are already lexical forms. At Plan they were P1#R5 and #R6, 2 of 13.

**After the draft (the conductor added this from the log)**

The facilitator's draft covers the log through qa@22:47. Two more security rounds followed.
- **review@2026-11-26 23:08 (security re-check):** S1-S3 closed. New blocker S8: the S2 fix trusted that a switch earlier in the line succeeds, so on main a failed `git switch -c <existing>` then `;` and a push was allowed. The guard before S2 refused it. The owner chose "Fix S8 now" (decision@23:08).
- **run@2026-11-27 09:14 (seeded S8):** 2 agents, 31,651 tokens, 1 cycle. S8 fixed (test 233280b1, fix 624ada13). QA (qa@09:14) then found Q1-Q3, three more holes from the same trust-the-switch design: a negated switch, a switch in another repository, `git --version switch`. Each one pushed main in a copy. The guard before S2 refused all three.
- **decision@2026-11-27 09:18:** "Always check the real HEAD". A push is refused when the real current branch or any switch target in the line is the base branch, and the `&&` detection goes.
- **run@2026-11-27 09:50 (seeded Y1-Y3):** 6 agents, 96,016 tokens, 3 cycles.
  - Cycle 1 closed Y1-Y3 with more parsing (ea00553c), not the ruled design. QA's blocker Q1 caught that, and cycle 2 applied the ruling (2821d5ef). Cycle 3 fixed Q4, a later switch hiding an earlier switch to the base branch (b55cd95f).
  - The net guard change is a deletion: `heads = {current_branch(at), *switched_to}`.
  - Q2 (`cd -`) and Q5 (a destination from `git -c remote.origin.push`) went to the backlog (2026-11-27-yolo-guard-push-forms-left).
- **Incident (note@2026-11-27 09:51):** an unquoted heredoc in the conductor's own shell ran S8's example commands. They created and pushed two stray branches, which the conductor deleted with the owner's approval. main was untouched.

- **After PR #37 (review@2026-11-27 10:39):** the repository's Claude review found P1 (a push that xargs runs), P2 (the probe ruling refused under YOLO) and P3 (a vacuous self-test). All three were fixed before the merge (decision@10:39; the P2 rejection was overruled at decision@12:19), in two seeded runs of 1 cycle each.

**Success criteria compared with outcomes (decision-2@13:30)**
- **YOLO runs unattended: not shown live.**
  - Not run: B21, B22, B24, B25, B26's model half, B51 and A1 are an owner-run list in note@20:02. Print mode has no AskUserQuestion (qa@20:02, the B26 probe).
  - Met headless: B17, B18, B23, B46, B59 and B45's reviewer half (qa@20:02).
- **MVP is visibly lighter (B43): ruled "Met" with nothing measured.** decision-4@21:43's question says "nothing measured yet", and the ruling's Next is "none". The measurement is follow-up 2026-11-26-measure-b43-b44-after-release (decision-3@21:43).
- **Main session stays lean (B44): the same.** decision-5@21:43 also says "not measured yet" and has Next: none.
- **Decisions are auditable:** the decision-record lint shipped in task 9 (run@17:56, C3 and C11). It is checked by the battery only (qa@22:47 criteria gaps).

**Record-keeping notes**
- **The specify cap's count:** decision@14:37 says 37 open questions, which matches review C3's 25 + 10 new plus 2 reopened. But capped@14:32's Deferred lists name only 35 rows (24 mechanism and 11 behaviour). C87 appears as A1, and C96 appears nowhere.
- **R9 at verify:** review@19:30#R9 found a wrong JUnit pointer in run@17:56. It was corrected in note@19:30.

## Reflections

**1. Most of Verify and Finish went to the guard's parser, and the defects came one form per pass.**
- **The redirect and escape chain:** each QA pass found the next spelling of the same constructs:
  1. qa@19:30#Q6: an escaped backtick, separator or space.
  2. #Q9: a quoted `<` or `>`.
  3. #Q10: a redirect glued onto a word.
  4. qa@20:02#Q11: `>|`.
  5. qa@20:02#Q12: `{fd}>`.
- **Command substitution, twice:**
  - review@19:30#R1 found that command substitutions hide the commands after them. The fix, b8b1e36c, is titled "Keep command start after a substitution".
  - review@22:19#S1 then found that words after an unquoted `$( … )` are dropped.
  - Both involve the same construct. Whether S1 already existed before b8b1e36c needs a `git show` this retro couldn't run.
- **A known pattern:** finding one hazard per pass is the pattern the worktree-management retro recorded for git refs ("Hazards were found reactively, one per pass").
- **A known lens gap:** the commit-guard retro (Reflections 1 and 4) recorded that security review found parser defects that code review had passed. That gap showed up here as S1-S3.

**2. Did the lexical scope draw the cost? The Out list held. The In list and the deny-list semantics drew it, about equally.**
- **Where the forms live:** C83 ("SimpleCommands: the lexical forms In and Out") was deferred as a mechanism row at capped@14:32. So the forms sit in the SimpleCommands contract (shape.md:306-309), not in Scope (shape.md:161-182) where specifying/SKILL.md:51 puts them, and no owner ruling covers them. The Codex Contracts review did probe them (M1#R4, M2#R15).
- **The fixed parser and guard findings fall into three buckets:**
  - **An In form handled wrongly (5 fixed, 2 deferred):** R1, Q6, Q9, Q10 and S1; Q11 and Q12 went to the backlog. In names whole constructs ("redirections dropped", "single and double quotes", "backslash continuations") and lists none of their spellings. So each unlisted spelling of an In construct counted as wrong behaviour, which is a blocker under verifying/SKILL.md:55.
  - **An Out form (0 fixed):** qa@22:47#Q4 (`$( )` as a destination) and #Q5 (`bash -c`) went straight to the backlog. Out cost no fix cycle.
  - **Not lexical (7 fixed):**
    - review@19:30#R2 and qa@19:30#Q7: gh global options.
    - qa@19:30#Q1: B54's refusal question.
    - S2: a push after a checkout on the same line.
    - S3: an `rm -r` with no visible operand.
    - The prior pass's Q1 and Q2 (qa@22:47 Fixed lines): a checkout of a remote-only branch, and xargs with a decoy operand.
    - These come from B52's deny-list semantics, which had no enumerated list of the ordinary commands it must refuse.
- **What S2 shows:** the Risks census (shape.md:732) looked for pd's own commands the guard might wrongly refuse. It did not look for the ones it must refuse.
  - S2's input is pd's own merge line from finishing-branch step 7 (review@22:19#S2).
  - That line first appears in the tests at `test_pd_yolo_guard.py:307`, as a hardcoded copy inside test_q1, added at c524af16, which is after the security review.

**3. Known debt in the reused module was rediscovered.**
- **The rediscovered items:** qa@22:47#Q7 (wrappers named by path, such as `/usr/bin/env`) and #Q8 (BSD `xargs -J/-R/-S`) are items already open in backlog line 2026-11-05-commit-guard-misses-wrapped-commits.
- **What happened:** B52 reused `commit_target.py` for a security deny-list. A commit reminder could live with these gaps; a deny-list can't. Neither shape.md's Risks nor its Out list cites the open commit_target backlog lines (grep of shape.md for `2026-11-05` finds nothing).
- **The differential that would catch the In-form defects is already filed:** the real-shell corpus differential in 2026-11-05-commit-target-test-debt-pin, merged from the commit-guard retro's Actions. A differential that runs bash with logging shims and compares the commands that actually run against the guard's verdict would catch R1, Q6, Q9, Q10, Q11, Q12 and S1 mechanically.

**4. The CHANGELOG commit tripped the verify gate because of a config gap that is already on the backlog.**
- **Timestamps:** 9a6c11b7 (21:43, phase to finish), then eefd27cf (21:45, CHANGELOG), then qa@21:51 (a full battery re-run). qa@21:51 says CHANGELOG.md counts as source "because this repository sets no source_paths". The security review entry cites 9a6c11b7. qa@22:47 later superseded the 21:51 run.
- **The same cause, twice in this item:** decision@21:43 put 10 untracked paths into `.git/info/exclude` "as on 2026-11-04". That is the same gap the worktree retro filed as 2026-11-04-pd-local-md-set-source, which is still open (backlog.md:7). `.claude/pd.local.md` has no `source_paths` (grep).

**5. Probe criteria were ruled with only two options.** B43 and B44 could be ruled only Met or Missed (decision-4 and -5@21:43). The honest state, "deferred to after release" (decision-3@21:43), had no ruling value. So the record now says Met for two of the four success criteria with no figures behind them.

**6. Fixes that trust state the line may not reach opened regressions; deleting the trust closed them.**
- **The S2 fix (142fc2fd) modelled the line's effect:** a switch earlier in the line changes which branch a later push leaves from. Every way that model can be wrong, where the switch fails or is skipped, then became a hole the old guard didn't have: S8, then qa@09:14#Q1-#Q3. Each fix patched one way (S8: the `&&` detection).
- **What closed the class was a rule, not more modelling:** check the real HEAD always, plus every target (decision@09:18, 2821d5ef, b55cd95f). It refuses more, and the owner accepted the cost.
- **The same shape appears in the S3 fix,** which refuses whenever xargs feeds an rm instead of parsing what xargs passes. Under B40, a deny-list guard should prefer the rule that refuses when unsure.

**7. The conductor's own shell is an attack surface for the commands it quotes.** Evidence strings for a shell-parser item are full of destructive commands in backticks. One unquoted heredoc ran four of them in the real checkout (note@09:51). YOLO was off for this session, so no guard stood in the way.

## Takeaways

Each landing below is proposed. None is landed in this item: an edit outside docs/dev_artifacts after Verify's last QA trips the verify gate (2026-11-26-verify-gate-trips-finish-s). Each one is a backlog line under Actions instead.

- **A deny-list hook is tested against the commands it exists to stop, taken from pd's own skills** -> check: `plugins/pd/hooks/tests/test_pd_yolo_guard.py`.
  - The test extracts every `git push`, `git merge`, `gh pr merge`, `git branch -D`, `git worktree remove` and `rm -r` line from `plugins/pd/skills/*/SKILL.md` and `plugins/pd/commands/*.md`, and asserts that the guard refuses each one under YOLO, unless it is a listed exemption (task worktrees, shape.md:732).
  - It replaces the hardcoded copy at `:307`, which can drift from finishing-branch.
  - Evidence: review@22:19#S2. Confidence: high.
- **A shell-parsing security hook is checked against real bash, not against more review passes** -> check: give the real-shell differential in 2026-11-05-commit-target-test-debt-pin a new target, `simple_commands` and the guard's verdict, and do it before more guard forms are fixed.
  - How it works: corpus lines run in a scratch repo under bash with logging shims for git, rm and gh. A destructive command that actually runs while the guard allows the line fails the test.
  - Evidence: the chain in Reflection 1 (R1, Q6, Q9, Q10, Q11, Q12, S1). Confidence: high for the lexical findings. It doesn't cover S2-style sequencing or path-named wrappers, which bypass PATH shims.
- **A lexical In list names the spellings it covers for each construct; anything unnamed is Out** -> skill edit: `plugins/pd/skills/specifying/SKILL.md:51`.
  - Proposed addition: "each In construct lists its spellings (for redirects: `>`, `>>`, `<`, `2>&1`, `&>`, glued `word>file`, `>|`, `{fd}>`), and an unlisted spelling is Out; In text next to an Out form (words after `$( … )`) needs its own case."
  - The same edit should say that this list stays in Scope for the owner's sign-off even when calvin defers it as a mechanism row (C83).
  - Why not CLAUDE.md: the rule already lives at specifying:51, and a CLAUDE.md copy would restate it.
  - Evidence: Reflection 2. Confidence: medium.
- **Reusing a module for a stricter purpose brings its open backlog into Risks** -> check (a pd-lint warning): for each `modules:` path in shape.md's contract blocks, look up open backlog.md lines that name its file stem, and warn when shape.md cites none of their ids.
  - Limit: line 14 says "commit guard", not `commit_target`, so a stem match finds lines 15 and 16 but not 14. If that limit is judged too weak, fall back to a line in the `designing` skill's review checklist.
  - Evidence: qa@22:47#Q7 and #Q8. Confidence: medium.
- **Set source_paths so the verify gate stops counting docs and untracked files** -> check (config): `.claude/pd.local.md`. This is the existing backlog item 2026-11-04-pd-local-md-set-source.
  - Evidence: decision@21:43 and qa@21:51. Confidence: high.
- **A probe criterion has a "Deferred" ruling besides Met and Missed** -> check: phase-gate.sh's finish rule for B61 (shape.md:533, :567).
  - A Met ruling must cite the note entry that holds its figures.
  - "Deferred" must name a backlog id.
  - Evidence: decision-4 and -5@21:43. Confidence: medium. Whether to accept this is the owner's call, since the owner chose Met.

- **A deny-list guard prefers a refuse-when-unsure rule to modelling what a command line will do** -> skill edit: the `verifying` skill's review checklist gains "a fix to a deny-list hook that predicts the line's effect (a switch, a cd) needs a case where the predicted step fails". Landing deferred: any edit outside docs/dev_artifacts trips the verify gate after QA (2026-11-26-verify-gate-trips-finish-s), so it is a backlog line. Evidence: Reflection 6. Confidence: medium.
- **Quote heredoc delimiters when the body holds backticks or $( )** -> landed in the conductor's memory (feedback_quote_heredocs.md, not a repo commit). Evidence: note@2026-11-27 09:51. Confidence: high.

## Actions

**Filed at finish:** 2026-11-27-yolo-guard-skill-command-corpus, 2026-11-27-pd-lint-warns-contract-modules, 2026-11-27-phase-gate-probe-ruling-deferred, 2026-11-27-pd-proof-empty-junit-first, 2026-11-27-specifying-lexical-lists-name-their, 2026-11-27-verifying-checklist-case-deny-list, 2026-11-27-yolo-guard-push-forms-left, 2026-11-27-yolo-guard-head-moves-untracked. The three edits to existing lines below were applied to backlog.md in the same commit.

- **New backlog lines** (each ending `(from: workitems/2026-11-26-stage-yolo-decisions-secretary-entry)`):
  - `yolo-guard-pd-skill-command-corpus`: drive pd's own push, merge, delete and remove lines from skills and commands through the YOLO guard and expect a refusal (S2).
  - `pd-lint-modules-open-backlog`: warn when a contract's module has open backlog lines that shape.md doesn't cite.
  - `phase-gate-probe-ruling-deferred`: a Deferred value for probe rulings, and a Met ruling must cite a note that holds figures.
  - `pd-proof-empty-junit-first-run`: the first post-merge proof run wrote a JUnit report with no tests for tasks 1, 3 and 8. A re-run passed each time (note, note-2 and note-3@17:56).
- **Edits to existing lines (no new ids):**
  - Merge 2026-11-26-verify-gate-trips-finish-s into 2026-11-04-pd-local-md-set-source, since one config change covers both.
  - Widen 2026-11-05-commit-target-test-debt-pin's real-shell differential to cover `simple_commands` and the YOLO guard's verdicts.
  - Mark the Q7 and Q8 parts of 2026-11-26-yolo-guard-forms-qa-found as duplicates of 2026-11-05-commit-guard-misses-wrapped-commits (full-path wrappers, BSD xargs `-J/-R/-S`).
- **Already filed by this item, not re-proposed:**
  - 2026-11-26-pd-commit-lint-misses-git
  - 2026-11-26-pd-read-budget-fast-path
  - 2026-11-26-qa-battery-self-test-loop
  - 2026-11-26-phase-gate-specify-failure-message
  - 2026-11-26-pd-stop-gate-finish-saves
  - 2026-11-26-phase-gate-specify-accepts-any
  - 2026-11-26-phase-gate-verify-s-risk
  - 2026-11-26-yolo-guard-parser-bypasses-left
  - 2026-11-26-measure-b43-b44-after-release
  - 2026-11-26-simplecommands-contract-wording-shape-md
  - 2026-11-26-yolo-guard-forms-qa-found
  - 2026-11-26-yolo-guard-security-review-warnings
  - 2026-11-26-verify-gate-trips-finish-s
- **Not backlog:**
  - After the merge, remove the `.git/info/exclude` block (decision@21:43).
  - Before relying on B21-B26, B51 and A1, run the owner-run live probes in note@20:02.

## Not checked

- **The fix-cycle split in run@19:30** comes from commit timestamp clusters, not logged cycle boundaries.
- **Whether S1 predates b8b1e36c** (the R1 fix) is unchecked.
- **The facilitator read only the two named earlier retros,** so the cross-references carry no ordinal labels.
- **The final security re-check** (review@2026-11-27 09:52+08:00) approved: S8 closed, S1-S3 hold; its notes S9 and S10 are older misses, on the backlog.
