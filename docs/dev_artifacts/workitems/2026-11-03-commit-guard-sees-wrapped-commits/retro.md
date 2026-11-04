# Retro: commit guard sees wrapped commits

## Trigger

Two triggers fired, both from `phase-gate.sh finish`.

- **Second backward move:** phase@2026-11-03 18:56+08:00 says "Second backward move: a retro is owed at Finish". The record holds six backward moves in all:
  1. **phase@2026-11-03 12:55+08:00, implement -> create-plan.** C25's `git merge-base main HEAD` baseline becomes HEAD on `main`. The worktree item's plan review found this (its N2).
  2. **phase@2026-11-03 18:56+08:00, implement -> create-plan.** The simplification review showed C25 failing a correct implementation on C8 and C24. C23's base was also unnamed for pull-request CI.
  3. **phase@2026-11-03 19:21+08:00, implement -> create-plan.** Calvin ran on plan.md (33 questions) and showed the premise of the C23 ruling was wrong.
  4. **phase@2026-11-05 04:26+08:00, verify -> design.** Contract changes for R6 and R7, and `$'…'` decoding for Q8.
  5. **phase@2026-11-05 04:57+08:00, create-plan -> specify.** A probe disproved the signed-off rule about `+` words.
  6. **phase@2026-11-05 06:14+08:00, finish -> verify.** The security review's S1: `$$'` read as an ANSI-C quote hid a top-level commit that `main` sees (review@2026-11-05 06:14+08:00).

  Moves 1 to 3 came before any code ran: each entry says "Nothing has executed".
- **Capped:** capped@2026-11-03 12:16+08:00 (design). review@2026-11-03 12:02+08:00#R4 was still open after three fix cycles.
  - The owner asked for one more pass (decision@2026-11-03 12:19+08:00).
  - The owner then accepted the revision (decision@2026-11-03 12:33+08:00).

## Aims

From shape.md `## Requirements` and note@2026-11-03 11:02+08:00 (PR #29's review notes):

- **See wrapped commits.** `plugins/pd/hooks/lib/commit_target.py` sees a `git commit` behind any wrapper in a 10-row table (`timeout`, `sudo`, `env`, `nice`, `stdbuf`, `time`, `command`, `exec`, `nohup`, `xargs`). It also sees one inside a `-c` script of five shells, at any depth. Then `pre-commit-guard.sh` gives its reminder and `pd-commit-lint.sh` lints the commit.
- **A bare trailing `--`.** `git checkout <x> --` with nothing after the `--` reads as `git checkout <x>`.
- **Must-nots** (shape.md:74-76): no traceback, no quoted prose seen as a commit, no added subprocess.
- **Size:** small mode, "two tasks at most" (phase@2026-11-03 11:02+08:00).

## Outcomes

**Delivered**
- **Three tasks merged, not two.**
  - Tasks 1 and 2: run@2026-11-03 19:42+08:00, commit 142ce000.
  - Task 3: run@2026-11-05 05:15+08:00, commit 23b5c9b3. It carried the rulings made after Verify run 1.
- **Size:** 59 commits (`git log --oneline main..HEAD` before this retro). 17 files, +1500/-23, of which `commit_target.py` has 175 changed lines and `test_commit_target.py` +564.
- **Verify passed twice:**
  - at 02c67b6a (phase@2026-11-05 06:06+08:00);
  - after the security review sent it back, at e6e4bf62 (phase@2026-11-05 06:36+08:00): all nine battery commands and the 48 `test_commit_target` tests (qa@2026-11-05 06:36+08:00).
- **Scope added after sign-off:**
  - `$'…'` decoding (decision-3@2026-11-05 04:26+08:00).
  - `+c` counts as `-c` (decision@2026-11-05 04:57+08:00).
  - The CHANGELOG check looks at the whole file, in three items' tests (decision@2026-11-05 04:26+08:00).

**Stage by stage**

| Stage | Window | Passes | Blockers | Notes |
|---|---|---|---|---|
| Criteria | 11-03 11:02-11:24 | 3 calvin cycles (review@11:10, @11:15, @11:22) | 4, 1, 0 | signed off at decision@11:24 |
| Design and plan, reviewed together | 11-03 11:24-12:33 | 5 codex passes (review@12:02, @12:07, @12:10, @12:16, @12:26) | 5 in the first pass; then R4 stayed open through the 4 scoped passes | capped@12:16 |
| Plan rework | 11-03 12:55-19:23 | simplification review@18:56; its QA, review@19:03; calvin on plan.md (note@19:23: 33 questions, 27 fixed, 5 answered, 1 dismissed) | 0, 1 (Q1) | moves 1-3; the owner ruled on C23 twice (decision@19:04, reversed at decision@19:23) |
| Implement, tasks 1-2 | 11-03 19:23-19:42 | run@19:42: 4 agents, 46,614 tokens, 0 fix cycles per task | — | |
| Verify run 1 | finished 11-04 20:55 | run@20:55: 6 agents, 57,185 tokens, 2 cycles | 6 (R1-R6), plus warning R7 | start time not recorded |
| Back to design and plan | 11-05 04:26-05:06 | review@04:38 (4 blockers); review@04:46 approved; calvin on task 3, review@04:58 (1 blocker, 15 warnings, 16 notes; 22 fixed, 10 answered); review@05:06 approved | 4, 0, 1, 0 | `+c` probe at decision@04:57 |
| Implement, task 3 | 11-05 05:06-05:15 | run@05:15: 3 agents, 22,361 tokens, 1 fix cycle | — | |
| Verify run 2 | 11-05 05:15-05:42 | run@05:42: 4 agents, 51,904 tokens, 1 cycle | 4 (R1-R4) | |
| Verify run 3 | 11-05 05:42-06:06 | run@06:06: 4 agents, 51,216 tokens, 1 cycle | 4 (R1-R4) | |
| Security review | 11-05 06:06-06:14 | review@06:14 (pd:security-reviewer, read-only) | 1 (S1), plus warnings S2, S3 | move 6 |
| Verify run 4 | 11-05 06:14-06:36 | run@06:36: 4 agents, 39,921 tokens, 1 cycle | 5 (R1-R5) | |

**Workflow cost**
- **Six runs:** 25 agents and 269,201 tokens in total.
- **The four Verify runs:** 18 agents and 200,226 tokens, about 74% of the total.
- **The work item as a whole:** 8,441,493 tokens by the `Stop` gate's count (the `metrics` entry).
- **Not counted per stage:** codex, calvin and security passes outside the workflows record no token figures.

**What each Verify pass found**

| Pass | Code defects | Test defects | Where the code defects came from |
|---|---|---|---|
| Run 1 (review@2026-11-04 20:55+08:00) | R2: an empty shell word raises IndexError. R3: a wrapper option with no value swallows the `;`. R4: a `$'…'` script goes unseen. Q8 (warning): `$'…'` escapes are not decoded. | R1: `trace.jsonl` left in the source tree. R5: 19 negative inputs untraced. R6: a CHANGELOG assertion that reads `[Unreleased]` and nothing else. | tasks 1 and 2 |
| Run 2 (review@2026-11-05 05:42+08:00) | R1: NUL. R2: the hook prefilters drop an escape-spelled `commit`. R3: byte escapes break UTF-8. | R4: two C29 inputs untraced | all three sit in, or behind, the `$'…'` decoding that decision-3 added |
| Run 3 (review@2026-11-05 06:06+08:00) | none | R1-R4: decoded-apostrophe re-quoting, `--long=value`, a `--long` shell flag, the lint prefilter (02c67b6a, tests only) | — |
| Security (review@2026-11-05 06:14+08:00) | S1: `$$'` read as an ANSI-C quote hides a top-level commit, a regression against `main`. S3: `env -` hides its command. S4: a lone surrogate in `$'…'` hides the whole command. | — | S1 and S4 sit in the decoding decision-3 added; S3 in the `env` row |
| Run 4 (review@2026-11-05 06:36+08:00) | R1-R3: S1, S3, S4 confirmed (e6e4bf62) | R4: separated wrapper values (`xargs -I {}`, `sudo -g`). R5: a one-digit `\xH` (19b799f9) | — |

After run 3, and again after run 4, QA's mutants still survived on single WRAPPERS entries (sudo `-h/-p/-T`, xargs `-d`) and on `~` (qa@2026-11-05 06:06+08:00 Q3, Q5; qa@2026-11-05 06:36+08:00). They went to the backlog (note@2026-11-05 06:06+08:00, note@2026-11-05 06:36+08:00).

**C25: one must-not, ten issue lines**
- **The must-not:** "must not add subprocesses" (shape.md:76). C25 proves it with a run-time trace, C27 with a static `ast` scan.
- **The issue lines C25 drew:**
  - review@2026-11-03 12:02+08:00#R4. The same issue then carried through @12:07#R1, @12:10#R1, @12:16#R1 and @12:26#R1.
  - review@2026-11-03 18:56+08:00#R1.
  - review@2026-11-04 20:55+08:00#R1 (the trace file leak) and #R5.
  - review@2026-11-05 04:38+08:00#R3.
  - review@2026-11-05 05:42+08:00#R4.
  - Also the Q7 fix (462ade63) and backward moves 1 and 2.
- **How the proof grew:** a `git` PATH shim plus a call-site count, then an audit hook, then fork events with negative controls, then a static `ast` scan plus a Popen check, then a differential trace against the fork point, and finally explicit git argv sequences.
- **The version the owner accepted at the cap was wrong.** It failed a correct implementation on C8 and C24 (review@2026-11-03 18:56+08:00#R1).

## Reflections

**1. The parsing surface was open-ended: confirmed, and the scope added at Verify carried most of the later defects.**
- **Criteria bounded the meaning of commands but not how they are spelled.**
  - Bounded: Scope Out lists `&&`/`||`, script files, `eval`, `env -S` and `ssh`.
  - Not bounded: ANSI-C quoting, `$"…"`, NUL, byte encodings and quote-split words were neither In nor Out. Run 1's R4 says so: "shape.md:39 does not exclude this quoting form."
- **Verify run 1's ruling opened the surface; it wasn't only discovered there.** Of the six code defects found after run 1, five sit in the `$'…'` decoding decision-3 added: run 2's R1 to R3, and the security review's S1 and S4. One of them, S1, is a regression: `main`'s parser sees that commit.
- **Code defects did not converge under the code review.** Run 3 found none, and the security review then found three. The difference was the lens: the security reviewer read the code against bash's own lexer (`parse.y` pairs `$$` before `$'`), and the code review read it against shape.md.
- **What would have bounded it earlier:**
  - **A "known limits" list of spellings under Scope Out.** This is the cheapest option. R4 and Q8 would have been a choice at Criteria (fix now, or backlog) rather than a fix-in-pass at Verify.
  - **A differential against the base parser.** Any input `main`'s `commit_target.py` sees and HEAD's misses is a regression by definition, and a corpus run finds it mechanically. S1 is exactly that input; the conductor's probe showed it in one command (review@2026-11-05 06:14+08:00#S1).
  - **A differential against the real shells.** Run 2's R1 ("Bash truncates the quoted word"), R3 ("Bash bytes are e4b8ad") and the five-shell probe (decision@2026-11-05 04:57+08:00) all compared against the real shell by hand. Confidence is medium: `sudo -u` and some other wrappers can't run in CI.
  - **A closed input grammar.** Not worth it: bash's own grammar is the thing being modelled, and D1 already rejected `bashlex` (shape.md:130).

**2. A probe disproved a signed-off criterion: confirmed.** The `+` rule passed three looks before anyone probed it.
- **Criteria calvin, cycle 3, row 7** (calvin-cycle-3.md:43) asked whether other `+` words are options. It was filed "ambiguity · note", and the conductor answered by rewording ("other `+` words are flags", review@2026-11-03 11:22+08:00). Step 4 of `plugins/pd/skills/specifying/SKILL.md:35` routes wording questions to the conductor and asks for no probe.
- **Calvin on plan.md, row 23** (plan-calvin-ledger.md:28) quoted the rule and asked which cases exercise it. That is a coverage question, not a question of whether the rule is true.
- **Verify run 1's QA** probed `bash +c 'git commit -m x'` and called the empty output "correct but unpinned" (qa@2026-11-04 20:55+08:00 Q3). It judged correctness against shape.md, not against bash.
- **Calvin on task 3, question 29** was filed "assumption" and asked "How do you know …? What was checked" (task3-calvin.md:38). That led to the probe.
- **So the category a question got decided whether anyone probed.**
  - The Criteria bar already asks for an inline REPL line on "stdlib or library runtime behavior" (specifying SKILL.md:47), but a shell's argument rules fall outside that wording.
  - The worktree item's design checklist line, "External output parsed" (designing SKILL.md on that branch, line 37), covers output a contract parses: "each git or CLI output a contract parses names the input variants it was probed against". This rule was about how a program reads its arguments, and it sat in Requirements, which design review doesn't re-prove. So that line would not have caught it.
- **The same mistake hit C23.** The conductor's Rejects of review@2026-11-03 19:03+08:00#Q1 called merge-base "a real check on the branch". Calvin then showed it fails on any later branch that edits either hook suite. The owner's ruling (decision@19:04) was re-asked and reversed (decision@19:23). planning SKILL.md:16 already requires a refutation at file:line, so this was a lapse in following the rule, not a gap in it.

**3. Tests that break at release: confirmed.**
- **The defect:** R6 (review@2026-11-04 20:55+08:00). C26 checked for the entry under `[Unreleased]`, which `scripts/release-pr.sh:36` empties at release. The same assertion sits in `test_pd_worktrees.py:407` and `test_explorer_codegraph.py:172` (decision@2026-11-05 04:26+08:00).
- **Its source:** plan.md:40 asked for it, and `plugins/pd/skills/updating-docs/SKILL.md:15` tells authors to put the entry under `[Unreleased]`.
- **Why it slipped through:** no pre-Verify review flagged it. The failure exists only after a release rewrites `CHANGELOG.md`, and Codex found it by applying that rewrite in memory.
- **Where a check belongs:** a CI step that runs the suite against the promoted file catches the whole class, however a test spells it. A lint over test text would have to chase spellings.
- **A side effect:** the fix copied the release awk into the test (test_commit_target.py:155-159), so the transform is now restated beside `release-pr.sh:36`.
- **Neither sibling retro has a CHANGELOG lesson** (checked by the conductor with `git show` of both branches' `retro.md`), so this one isn't a duplicate.

**4. Stopping the fix loop at the third run: right about test debt, wrong to read it as "no defects left".**
- **Why run 3 ran:** the conductor chose it (note@2026-11-05 05:42+08:00). Four surviving mutants (Q1, Q2, Q3, Q7) counted as blockers under "a criterion with no test that would catch its breaking" (verifying SKILL.md:55).
- **What it cost:** 4 agents, 51,216 tokens and about 24 minutes, for four test-only cases (02c67b6a) and no code defect.
- **Why the loop has no floor:** run 3's QA found four more survivors of the same kind, all behaving correctly today. A mutation sweep over a table of 10 rows and dozens of option entries keeps sampling new survivors, and SKILL.md:55 makes each one a blocker. Run 4's QA found survivors again (sudo `-h/-p/-T`, xargs `-d`).
- **The line drawn in note@2026-11-05 06:06+08:00 held for test debt:** what remained was single table entries in rows that already had a case.
- **But it was not evidence of correctness.** Mutation survivors measure the tests, not the parser. The security review found three code defects in code that three code reviews had passed (point 1). A different lens, not another run of the same one, found them.

**5. Proving the subprocess must-not.**
- **What drove the escalation:** each review pass produced a mutation that slipped the current proof, and each revision added machinery.
- **The must-not's wording invited a run-time proof.** shape.md:76 says "the only `git` calls stay today's", which is a run-time count. The harm it guards against is hook latency.
- **The static check was ready at the cap.** C27's `ast` audit (A1 in capped@2026-11-03 12:16+08:00) was in place, and A1 calls it a complete proof for this one-file module. The run-time trace still kept producing findings through Verify run 2, and once leaked a file into the source tree.
- **The security review confirmed the static proof** (review@2026-11-05 06:14+08:00#S8: only the three git queries, every path after `-C`).

**6. Scope contradicted Design.**
- **The contradiction:** shape.md:68 lists new `test-hooks.sh` (10c) and `test-pd-commit-lint.sh` cases as In, but D4 (shape.md:133) rejects them. Neither file changed (qa@2026-11-05 05:42+08:00 Q5; qa@2026-11-05 06:06+08:00 Q8; qa@2026-11-05 06:36+08:00 Q5).
- **Why review missed it:** designing SKILL.md:34 compares the parts of `## Design` with each other, not with Requirements' Scope.

**7. Minor: the merger's case_map slipped twice.**
- run@2026-11-03 19:42+08:00 misspelt a green test.
- run@2026-11-05 05:15+08:00 named C28 by file and gave C31 no test.

The conductor fixed both by hand. Nothing is proposed for this.

## Takeaways

Each lesson lands as a skill edit or a backlog item; the skill edits and the backlog lines are in commit 77401f23.

- **A rule about how an outside program behaves is a fact to probe, not wording to settle** -> skill edit, `plugins/pd/skills/specifying/SKILL.md`:
  - step 4 (`:35`) gains "A row asking how a program behaves is never a wording question: answer it with a probe, quoted in the cycle's `review` entry."
  - the Expectations bar (`:47`) extends the REPL-line rule to external-program behaviour (`$ cmd → output`).
- **A parser of another program's input names the spellings it leaves out** -> skill edit, `plugins/pd/skills/specifying/SKILL.md:51` ("Scope boundaries, both sides"): the lexical forms read and left Out (quoting, escapes, encodings, split words), not only the semantic ones.
- **Surviving mutants on single table entries are test debt, not blockers** -> skill edit, `plugins/pd/skills/verifying/SKILL.md:55`: one backlog line for all of them.
- **A parser rewrite is checked against the parser it replaces** -> skill edit, `plugins/pd/skills/verifying/SKILL.md:55`: an input the base parser handles and the new one misses is a blocker, and QA diffs the two over the case corpus when the change rewrites a parser. The corpus differential itself is a backlog item (Actions).
- **Rejecting a Scope In item moves it Out** -> skill edit, `plugins/pd/skills/designing/SKILL.md:34`, appended to "One design, no contradictions".
- **A test can break when a release rewrites `CHANGELOG.md`** -> backlog (Actions): it needs the promote transform shared before CI can call it.
- **Not landed: word a must-not as the property its cheapest proof checks** (medium confidence; one item's evidence).

## Actions

- **Filed by this retro** (backlog.md, in the landing commit):
  - 2026-11-05-ci-run-pytest-suite-changelog: CI runs the pytest suite on `CHANGELOG.md` as `release-pr.sh` promotes it.
  - 2026-11-05-commit-target-corpus-differential-tests: corpus differentials against `main`'s parser and the real shells.
- **Filed from the security re-check** (review@2026-11-05 06:40+08:00):
  - 2026-11-05-commit-target-lone-surrogate-raw: S5 and N1, a crash on a directory word lets the commit through.
  - 2026-11-05-commit-target-match-wrappers-basename: N2, `/usr/bin/env` and `/usr/bin/timeout`.
- **Already filed by this item, not re-proposed:**
  - 2026-11-05-commit-guard-ksh-93-runs
  - 2026-11-05-commit-hooks-commit-prefilter-drops
  - 2026-11-05-commit-target-normalize-printed-directory
  - 2026-11-05-commit-target-pin-untested-wrappers
  - the security review's S2 (`\u`, `\U`, `\cX`) and S6/S7 (BSD options, `--rcfile`, a tab in a directory) items
- **set-source-paths-test-paths** (qa@2026-11-05 05:42+08:00 Q4; qa@2026-11-05 06:36+08:00 Q4) belongs to the explorer item, and lands with the round's combined PR.

---
Drafted by `pd:retro-facilitator` from `log.md` and the git log at 9f2ef5af's predecessor; the conductor added move 6, the security review and Verify run 4 from their entries (review@2026-11-05 06:14+08:00, run@2026-11-05 06:36+08:00, qa@2026-11-05 06:36+08:00), and checked the sibling retros and the "External output parsed" wording with `git show`.
Self-labels: none beyond the log's own "Second backward move", quoted from the record.
