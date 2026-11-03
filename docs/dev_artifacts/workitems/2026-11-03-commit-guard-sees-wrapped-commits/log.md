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
