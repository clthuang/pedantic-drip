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
