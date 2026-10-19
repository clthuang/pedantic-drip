# `log.md` entry shapes

One block per entry kind (plan Part B §6). A work item's entries go in its `log.md`; a single-file item's go under its `## Log` section, which is the file's last section. `pd-lint`, `pd-status` and `phase-gate.sh` parse these shapes; change them here first.

## The rules every entry follows

- **Heading:** `## <YYYY-MM-DD> <HH:MM±hh:mm> <kind>[-<n>][ <rest>]`, the local time with its UTC offset. The kind is from the closed list: `decision`, `phase`, `review`, `qa`, `gate`, `run`, `handoff`, `replan`, `metrics`, `defect`, `note`, `capped`.
- **Same kind, same minute:** the second entry's kind gets `-2` (`review-2`), the third `-3`.
- **Append-only.** An entry is never edited after its commit.
- **References** to an entry are `<kind>@<YYYY-MM-DD> <HH:MM±hh:mm>`, plus `#<item id>` for one issue, follow-up or assumption inside it: `review@2026-10-14 11:30+08:00#R1`, `review-2@2026-10-14 11:30+08:00#R1`, `capped@2026-10-14 16:00+08:00#A1`.
- **`Closes: <ref>[, <ref>…]`** in a later entry closes a blocker or an assumption. A `review` or `qa` entry reporting the fix, a `decision`, a `capped` entry, or a backward `phase` entry that replaced the artifact may close one. A blocker with a proposed rejection closes only through a `decision` whose answer is the user's.
- **Issue lines** in a `review` or `qa` entry: `- <id> <blocker|warning|note> <file>:<line> — <claim>`. The ids are unique within the entry (`R1`, `Q1`).
- **Cited commits:** `Commit: <hash>` (or `Fixed by: <hash>` in a `defect`). `pd-lint` checks that each one exists.
- **Figures** come from a primary source, cited in the entry: a gate log, git, or the workflow run's `journal.jsonl`.
- **A converted legacy entry** carries a `Status: closed (legacy)` line; its blockers count as closed.

## The kinds

### decision
A ruling. The answer line is `A (user, verbatim): "<quote>"`, `A (conductor): <ruling>`, or `A (conductor, on the user's behalf): <ruling>` in a print-mode run. Criteria's sign-off asks exactly `Q: criteria signed off?`. A decision answering a cap stop adds `answers: capped@<YYYY-MM-DD> <HH:MM±hh:mm>`. A "continue" at the token cap raises the work item's budget with `Budget: workitem_token_budget=<n>` (the latest such line counts).

```markdown
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes, ship B1 to B4."
```

### phase
A phase transition. `(back)` marks a backward move, which names what it invalidates. Triage records each skipped stage, with the reason, in its own `phase triage -> <first stage>` entry.

```markdown
## 2026-10-14 15:40+08:00 phase verify -> design (back)
Reason: the contract named no error for an empty input.
Invalidates: plan.md.
Closes: review@2026-10-14 11:30+08:00#R2
```

### review
One review call's result: the reviewer, whether Codex fell back, the verdict, the commit reviewed and one issue line per finding. A proposed rejection is a `Rejects:` line with file:line evidence; it doesn't close the blocker.

```markdown
## 2026-10-14 11:30+08:00 review M1 — codex (fallback: no)
Verdict: changes requested. Commit: 6ccfa3a5.
- R1 blocker src/pd/parse.py:41 — an empty input raises KeyError, not the contract's EmptyInput.
- R2 warning src/pd/parse.py:88 — the retry loop is unused.
Rejects: review@2026-10-13 10:05+08:00#R3 — src/pd/io.py:12 already closes the handle.
```

### qa
One QA battery run: the commit it ran against, one `Ran:` line per `qa_battery` command, what passing each criterion would still allow, issue lines, a `Rejects:` line per proposed rejection of its own `Q` issues, and in Verify one `Fixed: <id> by <commit> — <test, or "removal">` line per fix, with a `Closes:` line naming the fixed review issues. Every `Rejects:` and `Closes:` ref names the entry that raised the issue.

```markdown
## 2026-10-14 12:30+08:00 qa
Commit: 6ccfa3a5
Ran: `uv run pytest -q --junitxml=agent_sandbox/junit/qa.xml` -> pass
Ran: `./validate.sh` -> pass
Criteria gaps: B2 — passing it still allows an unsorted result.
- Q1 blocker tests/test_parse.py:10 — no test covers B3's empty input.
```

### gate
A mechanical gate's result, with its figures and the raw log's path.

```markdown
## 2026-10-14 12:05+08:00 gate implement — pass
G1 4920/2, G2 51/1, G3 0/0. Raw logs: agent_sandbox/2026-10-14/m1/.
```

### run
A workflow launched or finished. A finished `implement-tasks` run lists each task it landed (a resumed run, only the ones it ran), each followed by an indented `case_map:` line; `phase-gate.sh implement` and Verify's reviewer read the task lines across every `run` entry, and a resumed run reads them back. A goal's first `run` entry records the original `workitem_token_budget` (or `unset`).

```markdown
## 2026-10-14 14:00+08:00 run implement-tasks — finished
Session: 0b5e…  Agents: 6. Tokens: 412000. Journal: ~/.claude/projects/…/journal.jsonl
Budget: workitem_token_budget=unset
- task 1: merged, proof pass, cycles 0, branch pd/2026-10-14-x/task-1
  case_map: C1=tests/test_parse.py::test_empty_input; greens: none; skipped: none
- task 2: merged, proof pass, cycles 1, branch pd/2026-10-14-x/task-2
  case_map: C2=tests/test_io.py::test_round_trip; greens: none; skipped: none
```

### handoff
What the next session needs that `## Now` can't hold.

```markdown
## 2026-10-14 18:00+08:00 handoff
Next: run /pd:verify. Open: R1 waits on the user's ruling.
```

### replan
At finish, for a work item listed in a roadmap: the plan still holds, or what changed (the roadmap edit lands in the same commit).

```markdown
## 2026-10-14 18:30+08:00 replan
Plan: plans/2026-10-14-thin-pd.md — still holds.
```

### metrics
Written once, at finish: the mode, and the `Stop` gate's token total for the work item.

```markdown
## 2026-10-14 19:00+08:00 metrics
Mode: standard. Tokens: 1210000 (source: ~/.claude/pd/gate/0b5e….json).
```

### defect
A defect found after the merge, naming the commit that fixed it. On a done work item, a retro is owed until `retro.md` exists.

```markdown
## 2026-10-20 10:00+08:00 defect
The parser accepted a trailing comma. Fixed by: 9f2c1a7e.
```

### note
Anything else worth keeping: a flaky test, a small work item's overrun, finish's no-retro note.

```markdown
## 2026-10-14 13:00+08:00 note
Flaky: tests/test_io.py::test_timeout failed once, passed twice.
```

### capped
A loop reached its cap. Four lists, each `none` or `- ` items. Every follow-up has its `backlog.md` line, with `(from: workitems/<id>)`. Assumptions get ids, for `Closes:`.

```markdown
## 2026-10-14 16:00+08:00 capped verify
Deferred:
- R4: the retry policy, left for a follow-up.
Follow-ups:
- 2026-10-14-retry-policy
Decisions: none
Assumptions:
- A1: callers never pass a negative timeout.
Closes: review@2026-10-14 11:30+08:00#R4
```
