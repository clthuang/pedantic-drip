# Retro: worktree management in pd

## Trigger
`phase-gate.sh finish` fired two triggers:
- **Backward moves.** log.md has four `(back)` phase entries:
  - `phase@2026-11-03 18:57+08:00`: implement -> design. Cause: the simplification review. Nothing had executed.
  - `phase@2026-11-03 19:24+08:00`: implement -> design. Cause: calvin on plan.md. Nothing had executed.
  - `phase@2026-11-04 16:04+08:00`: verify -> design. Cause: Verify run 1's R1.
  - `phase@2026-11-04 17:43+08:00`: verify -> specify. Cause: Verify run 2's QA findings Q5, Q6, Q8 and Q9.
- **Capped.** There are two `capped` entries:
  - `capped@2026-11-03 11:34+08:00`: the Criteria calvin loop, at cycle 3.
  - `capped@2026-11-03 12:57+08:00`: the plan review, where M1 arrived in the re-review after the third fix cycle.

## Aims
The owner's Clarify ruling (`decision@2026-11-03 11:08+08:00`) chose two things: "One cleanup script" and "Show leftovers in pd-status". Removing worktrees inside the workflow was not chosen, nor was tidying this repo's `.pd-worktrees/` remnant.
"Done means" in shape.md:22: after a run plus Finish or abandon, these are all gone except what the script reported as kept:
- every worktree on a `pd/<id>/task-*` branch;
- every stray that loses no commit when deleted.
Anything left over shows at session start.
The round's scope (`note@2026-11-03 11:02+08:00`, `note@2026-11-03 13:40+08:00`) was "investigate, design and plan". Execution came later, on the owner's ask quoted in `review@2026-11-03 18:57+08:00`.

## Outcomes
**Delivered.**
- **New script:** `plugins/pd/scripts/pd-worktrees`, 169 lines.
- **Shared helpers:** in `pd_common.py`, +44 lines.
- **pd-status:** a Leftover worktrees section, 60 lines changed. Session start passes the section on.
- **Callers:** implementing step 5, the wrong-test move, finishing-branch and abandon-workitem now run pd-worktrees.
- **Tests:** four files totalling 1,076 lines: `test_pd_worktrees.py` 565, `test_pd_status_leftovers.py` 273, `test_worktree_callers.py` 127, `conftest.py` 111.
- **Branch totals:** 27 files changed, +2,342 / −26 (`retro-diffstat.txt`), over 74 commits from `c5d721c4` to `19b3f49d` (`retro-gitlog.txt`).
**Stage timeline** (wall clock, which includes the owner's pauses):
| Stage pass | From -> to | Span | Notes |
|---|---|---|---|
| Criteria (1) | `phase@2026-11-03 11:02` -> `11:59` | 57 min | Calvin cycles 1-3 found 7 -> 3 -> 2 blockers (`review@11:19`, `11:28`, `11:34`); capped; owner accepted (`decision@11:58`) |
| Contracts (1) | `11:59` -> `12:40` | 41 min | Codex found 10 -> 4 -> 1 blockers (`review@12:21`, `12:34`, `12:38`); N3 closed by the owner (`decision@12:40`) |
| Plan (1) | `12:40` -> `13:40` | 60 min | Codex found 6 -> 1 -> 1 -> 1 blockers (`review@12:49`, `12:52`, `12:54`, `12:57`); capped; 43 min of the span was the wait for the owner's ruling |
| Parked | `13:40` -> `18:57` | — | No Execute this round (`note@13:40`) |
| Simplification -> design (back) | `18:57` -> `19:01` | 4 min | 0 blockers, 2 warnings; QA-approved (`review@19:01`) |
| Calvin on plan.md -> design (back) | `19:24` -> `19:27` | 3 min | 52 questions: 46 fixed, 6 answered (`note@19:26`); no review entry between 19:24 and 19:27 |
| Execute (tasks 1-3) | `19:27` -> `19:58` | 31 min | `run@2026-11-03 19:57`: 6 agents, 79,674 tokens, every task proof pass, 0 cycles |
| Verify run 1 | `19:58` -> `2026-11-04 16:04` | overnight | `review@2026-11-04 14:09`: 8 blockers, 1 warning; `qa@14:09`: 9 Q items |
| Back-move loop A | `16:04` -> `16:30` | 26 min | Design approved on its first pass (`review@16:09`); plan 2 -> 0 blockers (`16:19`, `16:21`); task 4 (`run@16:29`: 2 agents, 15,417 tokens) |
| Verify run 2 | `16:30` -> `17:43` | 73 min | `review@16:44`: 2 blockers; `qa@16:44`: 9 Q items, including Q8 |
| Back-move loop B | `17:43` -> `18:34` | 51 min | Calvin 5 -> 2 -> 0 blockers (`review@17:49`, `17:53`, `17:56`); design 1 -> 0 (`18:14`, `18:16`); plan 3 -> 0 (`18:22`, `18:25`); task 5 (`run@18:34`: 2 agents, 17,797 tokens) |
| Verify run 3 | `18:34` -> `19:06` | 32 min | `review@18:57`: 2 blockers; `qa@18:57`: 4 notes |
| Finish | `19:06` -> `19:10` | 4 min | Security review approved with 4 notes (`review@19:10`) |
**Review and run counts.**
- **Review entries:** 26 in total.
  - 6 calvin-runner cycles, in two loops of three.
  - 19 Codex passes.
  - 1 security-reviewer pass.
  - Calvin on plan.md was a single pass recorded as a note (`note@2026-11-03 19:26+08:00`), not a review entry.
- **Blocker lines:** calvin 19 (7+3+2+5+2+0); Codex 42 (design 15, plan 9, Verify 12, back-move loops 6). The 42 include `review@12:38#R1`, which carries `review@12:34#N3` forward.
- **Verify:** three runs (`run@2026-11-04 14:09`, `16:44`, `18:57`), each with 1 fix cycle, 4 agents each, 127,731 tokens together.
- **Execute:** five tasks over three runs, 10 agents, 112,888 tokens. Every task was proof pass with 0 cycles.
- **Tokens:** workflow runs total 240,619 tokens. The whole work item used 9,570,778 tokens (`metrics@2026-11-04 19:10+08:00`), so the workflows were about 2.5%. The rest went to the conductor and the review and calvin dispatches.
**Git-ref hazards, found one per pass.** Eight distinct hazards in how git refs are named or printed surfaced across seven entries:
| Hazard | Found at | Stage |
|---|---|---|
| A symbolic `worktree-wf_*` ref: `update-ref -d` deletes its target | `review@2026-11-03 12:34#N1` | Contracts |
| `%(refname:short)` prints `heads/<name>` when a tag has the same name, so a stray vouches for itself | `review@2026-11-04 14:09#R1` | Verify run 1 |
| A symbolic ref outside the stray namespace vouches for a stray | `review@2026-11-04 16:44#R1` | Verify run 2 |
| The `refs/heads/worktree-wf_*` pattern in `for-each-ref` doesn't cross `/`, while `git branch --list` does | `qa@2026-11-04 16:44#Q5` | Verify run 2 |
| Deleting a stray leaves a symbolic branch that points at it dangling | `qa@2026-11-04 16:44#Q9` | Verify run 2 |
| `%(symref)` names a chain's last ref, not the next link | `review@2026-11-04 18:14#R1` | Contracts (loop B) |
| `pd_common.git()` strips the last line's trailing space (pd_common.py:141), so a branch sorting last can't vouch | `note@2026-11-04 18:34`, `review@2026-11-04 18:57#R1` | after task 5 / Verify run 3 |
| A non-UTF-8 refname raises an error (`text=True`, strict decode) | `review@2026-11-04 19:10#S3` (open note) | Finish |
**Candidate threads, tested against the record.**
1. **Both Verify-to-earlier moves came from git-ref contract gaps: confirmed, with one exception.**
   - The 16:04 move rests on R1, the same-named tag. The other items riding on that move (Q3, Q7, Q8 of `qa@14:09`) were usage errors and a signature mismatch.
   - The 17:43 move's stated reason is Q9's new output line. Q5 and Q8 are also ref-handling; Q6 (BrokenPipeError) is not.
   - Design-stage probes did run (`review@2026-11-03 12:21` R1 and R2, `12:34` N1 and N2, all on git 2.54.0), but only in reaction to each finding. No list of ref variants was walked.
   - A design-stage probe list would plausibly have caught the tag, the symbolic voucher, the slash and the chain. It could not have caught the trailing-space defect, which Verify run 2's fixer introduced (`note@2026-11-04 18:34+08:00`: "From Verify run 2's fix 1f0246ec"). Only a shared fixture that every test runs against catches that kind.
2. **A Verify fixer changed a contract without a decision: confirmed.**
   - `qa@2026-11-04 16:44#Q8`: commit `1f0246ec` changed pd-worktrees' `--format` to `%(refname) %(symref)` and added a no-vouch rule, with no shape.md edit and no decision.
   - The fixer prompt already forbids this (`plugins/pd/workflows/verify-change.js:95`: "a fix that needs a criteria or contract change goes back as a rejection").
   - Verify run 1's fixer obeyed that rule for R1 (`review@2026-11-04 14:09` Rejects line). Run 2's fixer didn't.
   - Cost: Q8 went into the 17:43 back-move ruling (`decision@2026-11-04 17:43+08:00`), and the same commit `1f0246ec` shipped the B6 trailing-space defect that Verify run 3 had to fix (`b5075961`).
3. **The verify gate counted the owner's untracked files: confirmed.**
   - `decision@2026-11-04 19:06+08:00`: 11 untracked paths (`.codegraph/`, `.pd-worktrees/`, `docs/workflow-*`) went into `.git/info/exclude` as a temporary fix.
   - Cause: `.claude/pd.local.md` has no `source_paths`. `phase-gate.sh:136-142` then falls back to counting every changed or untracked path outside `artifacts_root`, `ls-files --others` included.
   - The same missing key makes `pd-lint --isolation` skip (pd-lint:556-557). That shows up in all three QA entries (`qa@14:09#Q9`, `qa@16:44#Q3`, `qa@18:57#Q4`), so task isolation went unverified for the whole item.
**Other recorded patterns.**
- **Tests that pass at the first commit (greens), undeclared, hid vacuous tests.**
  - Tasks 1-4 reported five undeclared greens: C23, C26, C27, C29 outside git (`run@2026-11-03 19:57`) and `test_c42_usage_errors[args3]` (`run@2026-11-04 16:29`).
  - Two were later shown to prove nothing:
    - C27, by `review@2026-11-04 14:09#R7`.
    - C42's only slash input, by `qa@2026-11-04 16:44#Q4`. That made it the second finding on the surviving `/` guard mutant, after `qa@14:09#Q3`.
  - pd-proof reports greens rather than failing them (pd-proof:59), and the merger passes them by name (merger.md:25).
  - Tasks 4 and 5 declared their expected greens in plan.md, and none of those was later found vacuous.
- **The plan review's last three fix cycles all landed on one case.** C30, the git-call budget, at plan.md:65: N1 (`review@12:52`), N2 (`12:54`) and M1 (`12:57`). M1 was a restated literal: C30's argv lacked the `--format` that shape.md:197 pins. CLAUDE.md's "Author-restated literals drift across artifacts" line already covers this; it is a recurrence, not a new lesson.
- **Calvin's Design changes were never reviewed.** The edits from calvin on plan.md entered implement with no review entry (`phase@2026-11-03 19:24` -> `19:27`). Verify run 1's R5 (a failed lookup taken for a gone branch) sits in the code path one of those edits defined. But it is an implementation fault against a contract that already said "otherwise exit 2", so no Verify finding traces to a gap in the unreviewed design.
- **The risk-scan false positive was raised four more times after it was cleared.** It matched `token` as a loop variable (risk-patterns.md:11). The owner cleared it at `decision-2@2026-11-04 16:04+08:00`, yet it came back as a note in `qa@16:44` (Q1, Q2) and `qa@18:57` (Q2, Q3).
- **The caller checks stay prose-only.** B18's caller tests check literal substrings in order. All three QA entries name that as a gap (`qa@14:09`, `qa@16:44`, `qa@18:57`, criteria-gap lines).

## Reflections
- **One concept carried the git-ref surface: the stray.** Strays (`worktree-wf_*` branches) are deleted when another branch vouches for them by containment. That rule pulls in containment, compare-and-delete, symbolic refs and chains, tag ambiguity and glob semantics. Of the four post-implementation blockers that touched stray deletion (`review@14:09#R1`, `#R5`; `review@16:44#R1`; `review@18:57#R1`), and of both Verify back-moves, nearly all trace to that rule. Stray deletion entered at calvin cycle 1 (`review@2026-11-03 11:19#R5`) as part of "cleanup". Neither the owner's ruling nor the simplification review (`review@2026-11-03 18:57`) weighed a list-only alternative for strays, where pd-status shows them and the user deletes them by hand.
- **Hazards were found reactively, one per pass.** Each reviewer probed the case in front of it on git 2.54.0, correctly. But no artifact listed the ref variants to probe, so each pass found the next one (table above). Twelve Verify-stage Codex blocker lines and two back-moves are the price of not walking that list once.
- **The fixer's rule exists, but its trigger is judgment.** The run 2 fixer seems to have treated "skip symbolic refs" as a code change because it touched only code, even though the format string it changed is pinned in shape.md's GitSurface. QA caught it (Q8), but only as a warning.
- **A config gap cost two things.** One missing `source_paths` key made the verify gate fail for the wrong reason, and silently disabled the isolation check for the whole item.
- **The proof machinery already flagged the vacuous tests.** Both vacuous tests were on the merger's greens list at merge time. The signal was there; nothing required anyone to justify it.

## Takeaways
Each lesson lands, in preference order, as a check, then a CLAUDE.md line, then a skill or prompt edit. Commits are pending; the conductor applies them.
- **Every git-parsing script test should run against one hostile-refs repository**, not hazards found one per review. The fixture would hold a tag named like a branch, a symbolic ref, a symbolic chain, a `/` in a stray name, and a plain branch sorting last. That would have caught `review@14:09#R1`, `16:44#R1`, `qa@16:44#Q5`, `#Q9` and the trailing-space defect in `1f0246ec` before review -> check: `plugins/pd/scripts/conftest.py` (a shared fixture; see Actions).
- **Undeclared first-commit greens should block the merge.** Two of five undeclared greens later proved vacuous (`review@14:09#R7`, `qa@16:44#Q4`); declared greens in tasks 4 and 5 drew no such finding -> check: `plugins/pd/scripts/phase-gate.sh` implement step. Proposed rule: "a `greens:` test in a `run implement-tasks` entry fails the gate unless plan.md's task names it as an expected green". Backlog in Actions.
- **Configure this repo's source and test paths** so the verify gate stops counting the owner's untracked files and `pd-lint --isolation` actually checks something -> check (config): `.claude/pd.local.md`. Proposed lines: `source_paths: [plugins/, scripts/, .github/]` and `test_paths: [plugins/pd/scripts/, plugins/pd/hooks/tests/, plugins/pd/workflows/tests/]`. Prove it two ways:
  - `pd-lint --isolation b230ae35..HEAD` reports files rather than "isolation skipped".
  - `phase-gate.sh verify` passes with the temporary exclude block removed.
  - Caveat: the paths are a proposal; I haven't tried them against pd-lint:570's "test file outside test_paths" rule.
- **Know git's ref-output traps before parsing it** -> CLAUDE.md line, under `## Gotchas`: `/Users/terry/projects/pedantic-drip/CLAUDE.md`. Proposed line: "**Parsing git ref output:** read `%(refname)` and drop `refs/heads/`, never `%(refname:short)` (a same-named tag prints `heads/<name>`); `%(symref)` names a symbolic chain's last ref, so read a branch's own target with `git symbolic-ref --no-recurse`; `for-each-ref` globs don't cross `/` but `git branch --list` globs do; `pd_common.git()` strips its whole output (pd_common.py:141) and decodes strict UTF-8, so a trailing empty field on the last line is lost."
- **The design stage should name the input variants it probed for every external output a contract parses** -> skill edit: `plugins/pd/skills/designing/SKILL.md`, `## Review checklist`. Proposed line: "**External output parsed:** each git or CLI output a contract parses names the input variants it was probed against (for refs: a same-named tag, a symbolic ref and a chain, a `/` in the name, a last line with an empty trailing field), with the command and tool version; a variant left unprobed is a blocker." This is the generic form of the CLAUDE.md line; it reaches the Codex reviewer, which CLAUDE.md doesn't.
- **A fixer edit to a pinned argument list or output format is a contract change**, even when only code changes (`qa@16:44#Q8`, `1f0246ec`) -> prompt edit: `plugins/pd/workflows/verify-change.js:95`. Proposed addition after "for the user to rule on.": "Changing an argument list, output format or rule that a contract block in shape.md pins is a contract change, even when no artifact is edited." Also mark QA's contract-drift finding as a blocker, not a warning. No mechanical check can decide what counts as a contract change, so this stays prose.
- **Calvin on plan.md should run before the plan review call, so its Design edits get reviewed** (`phase@2026-11-03 19:24` -> `19:27`, no review entry). Confidence is medium: no defect traces to it -> skill edit: `plugins/pd/skills/planning/SKILL.md`. Proposed line: "If calvin runs on plan.md (the owner's rule before execution), run it before the review call; any `## Design` change it makes goes through the review call too."

## Actions
The `pd-new backlog` lines get their backlog.md ids when run.
- `pd-new backlog "conftest: a hostile-refs repository fixture (same-named tag, symbolic ref and chain, slash in a stray name, last-sorting branch) that every git-parsing script test runs against"`
- `pd-new backlog "phase-gate implement: fail a first-commit green that plan.md does not declare as expected"`
- `pd-new backlog "pd_common.git(): keep the last line's trailing whitespace and decode refnames losslessly (review@2026-11-04 19:10#S3, qa@2026-11-04 18:57#Q5)"`
- `pd-new backlog "pd-lint --risk: stop re-raising a security signal the owner cleared by decision (decision-2@2026-11-04 16:04+08:00)"`
- **Remove the temporary `.git/info/exclude` block** (the BEGIN/END markers, 11 paths) after the round's combined PR merges, per `decision@2026-11-04 19:06+08:00`. Then set `source_paths` and `test_paths` in `.claude/pd.local.md` (Takeaways) so the block isn't needed again.
