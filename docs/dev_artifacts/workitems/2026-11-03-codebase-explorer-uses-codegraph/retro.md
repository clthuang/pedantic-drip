# Retro: codebase-explorer uses CodeGraph

<!-- Written at finish only when log.md records a retro trigger. Every figure is re-derived from log.md and git. Format: plugins/pd/references/doc-format.md. -->

## Trigger

Two triggers fired.

- **Second backward move:** `phase@2026-11-03 19:23+08:00` (`implement -> design (back)`). The first one was `phase@2026-11-03 18:56+08:00` (`implement -> create-plan (back)`). Both entries say "Nothing has executed."
- **Capped:** `capped@2026-11-03 11:29+08:00`. The calvin loop at Criteria reached its three-cycle cap. The owner then asked for a fourth cycle (`decision@2026-11-03 11:31+08:00`, "Run a 4th calvin cycle") and ended the loop after it (`decision@2026-11-03 12:05+08:00`).

## Aims

- **The explorer asks CodeGraph first.** `pd:codebase-explorer` calls `mcp__codegraph__codegraph_explore` before Glob, Grep and Read. It falls back to them when CodeGraph is unavailable, and reports how it searched in a new `search` field (shape.md `## Requirements`, Goals; B3 to B6).
- **The explorer's tools are pinned.** `validate.sh` gains a new `explorer` role (B1, B2).
- **A checklist line for renames.** The `designing` and `planning` review checklists gain one line: a rename or store move lists its surfaces, found by a call-graph query plus a grep for each old name. This folds in backlog #078 (B7).

## Outcomes

**Criteria (specify, 11:02 to 12:05 on 2026-11-03)**

- **Four calvin cycles; blockers fell 9, 3, 3, 1** (16 in total), from `review@2026-11-03 11:12`, `11:21`, `11:29` and `12:05+08:00`.
  - Warnings were 11, 8, 4 and 7.
  - Notes were 4, 8, 7 and 10.
- **The owner's extra fourth cycle earned its cost.**
  - Its one blocker was that the MCP no-index answer had been checked only with the CLI. `review@2026-11-04 19:47+08:00` confirmed that claim later, from the saved B4 stream.
  - It also tested three assumptions with real headless sessions instead of arguing them. That closed `capped@2026-11-03 11:29+08:00#A1`, and A1 then held at Verify (`note@2026-11-04 19:22+08:00`).

**Design and plan (small mode, joint review)**

- **One Codex review with 3 blockers, then a clean scoped re-review** (`review@2026-11-03 12:14+08:00`, `review@2026-11-03 12:19+08:00`). One fix cycle of three was used.
- **A commit claimed fixes that were not in it.** Commit 97e8cdf6 recorded fix cycle 1 as applied, but the edit script had stopped at its first check and changed nothing. The edits actually landed in 5bbb5e07 (`note@2026-11-03 12:15+08:00`).

**The two backward moves**

- **Backward move 1:** the owner asked for a simplification review after the plan had passed its gate. That review returned one note-level cut (`review@2026-11-03 18:56+08:00#R1`), and making the cut meant moving back to create-plan. A QA re-review approved the change (`review@2026-11-03 19:01+08:00`).
- **Backward move 2:** calvin on plan.md (the owner's rule between plan and execution) also ran after the move to implement. It raised 32 questions: 22 fixed, 8 answered, 2 dismissed (`note@2026-11-03 19:24+08:00`). Two of the answers changed `## Design`.
- **Cost of the two moves:** 4 extra phase entries and 2 extra Codex calls, between 18:56 and 19:24 on 2026-11-03.

**Implement**

- **One task, merged cleanly:** 0 fix cycles, 2 agents, 16781 tokens (`run@2026-11-03 19:32+08:00`, merge fe331ca9). 14 proving tests passed after the merge (`phase@2026-11-03 19:33+08:00`).

**Verify**

- **Live checks B3 to B6 all held at 3f0142f0** (`note@2026-11-04 19:22+08:00`).
  - In B3 the explorer made exactly one search call, the CodeGraph query (`b3.jsonl:29`, `"tool_uses":1`, last tool `mcp__codegraph__codegraph_explore`).
- **verify-change run 1:** 6 agents, 47823 tokens, 2 cycles (`run@2026-11-04 19:47+08:00`). It ended with one blocker and one warning.
  - **R1 (blocker):** the explorer's reply was not one JSON object alone. Fixed by test edb60e6c, then fix 669643b6.
  - **Q2:** a code fence around the reply. Fixed by test 951583ee, then fix 99e4b4cc.
  - **Q5 (warning):** line 67 sent skipped items to "a finding", which has no file to cite.
- **verify-change run 2, ordered by the owner:** 4 agents, 27977 tokens, 1 cycle (`run@2026-11-04 20:10+08:00`). It fixed Q5 as R1 (test 1516ed20, then fix dc79ae4b).
- **Notes still open at finish:** five, Q2 to Q6 of `qa@2026-11-04 20:10+08:00`.
- **Workflow token total:** 16781 + 47823 + 27977 = 92581. The calvin and Codex review calls are not on `run` entries; the whole work item used 5,172,211 tokens (`metrics@2026-11-04 20:12+08:00`), so the workflows were about 1.8%.

**Git**

- **37 commits** on `main..HEAD` (retro-gitlog.txt).
- **15 files, +693/−15** (retro-diffstat.txt).
  - Agent, `validate.sh`, skills, CI, CHANGELOG and docs: 45 changed lines.
  - The new test file: 194 lines.
  - The work item's own documents (log, shape, plan, README): 453 lines.

## Reflections

**Thread 1, the reply format: confirmed, with a cause the record never names.**

- **Three fixes, each proven only by wording tests.** R1, Q2 and Q5 were each fixed in turn, and each fix is proven by a C12 test that checks only the agent's instruction text. `qa@2026-11-04 19:47+08:00` says "Like R1's test, C12 checks only the instruction text". `qa@2026-11-04 20:10+08:00` says "Every agent-text test (C5 to C7, C10 to C12) pins instruction text only".
- **The live replies were nondeterministic.** At 3f0142f0, with the same agent text:
  - B3 and B4 handed back bare JSON (`b3.jsonl:33`, `b4.jsonl:39`).
  - B5 and B6 added trailing prose: "Skipped: non-Python callers … so the risk is low" (`b5.jsonl:37`) and "Skipped: fuzzy or near-miss spelling searches. Risk: …" (`b6.jsonl:37`).
- **Likely cause: a user-level hook.** The sessions' SessionStart hook injects "End your reply with one or two lines: what you skipped or did not check, and any risk the user must know" (`b5.jsonl:17`, and once in each of b3 to b6). The trailing lines follow that rule's exact shape.
  - Run 1's fix for R1 sent "anything skipped" to `no_findings_reason` "or a finding". That fixed one symptom and created Q5.
  - Q6, open at finish, shows the same pressure again: skipped-item notes now ride inside findings that do have a valid source.
- **The saved streams show no fence from the explorer.** The only fence in them is the outer session's own relay (`b3.jsonl:41`, `parent_tool_use_id: null`). Q2's description is missing from log.md (the qa entry keeps only a `Fixed:` line), so where the fence was seen can't be re-derived.
- **Does pd need a parser over real replies? Not for its consumers; possibly as a Verify check.**
  - No code parses the explorer's own output. Its dispatchers are the conductor and skills (`designing/SKILL.md:13`, `researching/SKILL.md:12`, `brainstorming/SKILL.md:21`). `research-fanout` replaces the reply with its own enforced schema (`research-fanout.js:25`).
  - So the strict "JSON alone" contract (shape.md:83) has an LLM reader and no machine consumer. It cost three Verify fixes without changing behaviour reliably.
  - Run 1's reviewer had asked for the parser: "validate the complete explorer handback, including trailing content" (`review@2026-11-04 19:47+08:00#R1`). The fix delivered instruction text instead.
  - The choice is to loosen the contract to how its reader reads it, or to keep it strict and check saved replies mechanically (Actions).

**Thread 2, the owner's re-run for a warning: confirmed as worth it, with a caveat.**

- **Cost:** 27977 tokens, 4 agents and 16 minutes (from `decision@2026-11-04 19:54+08:00` to `run@2026-11-04 20:10+08:00`). That is 30% of the item's workflow tokens.
- **What it found:**
  - The reviewer raised Q5 again as a blocker (`review@2026-11-04 20:10+08:00#R1`), because a finding with no `<path>:<line>` breaks the ExplorerDispatch `source` shape.
  - In the B3 re-drive, the sourceless "not traced" finding (:211) was gone.
- **Caveat:** the run again proved wording, not behaviour, and Q6 is the evidence of that. Logging the warning to the backlog instead would have shipped a line that breaks the contract.

**Thread 3, the empty CodeGraph answer: confirmed. The plan introduced the gap.**

- **The rule as written:** `codebase-explorer.md:75` counts a CodeGraph call only when it "answered (returned results)". An answer of "No relevant code found" is neither a result nor one of the three unavailable reasons.
- **What the shape intends:** an empty answer counts as answered. shape.md:28 says "one that answered counts", and B6 requires `search` to start with `codegraph` for an unknown name (shape.md:42).
- **Where it came from:** plan C10 (plan.md:26) pinned the gloss `answered` with `returned results`, and the test literal now holds it in place. This is the CLAUDE.md "author-restated literals drift" class, one layer down.
- **How long it stayed open:** through both Verify runs, as `qa@2026-11-04 19:47+08:00#Q1` and then `qa@2026-11-04 20:10+08:00#Q2`. B6 holds only because the explorer happens to read an empty answer as answered.

**Other observations**

- **Both backward moves came from gates outside the planning stage's exit.** Calvin on plan.md and the owner's simplification review both ran after `create-plan -> implement`. Neither found a defect that needed code; both needed plan or design edits, so both needed a backward move.
- **A recurrence of "claims trail verification".** The 97e8cdf6 log entry recorded a fix that had not happened (`note@2026-11-03 12:15+08:00`). The conductor caught it itself one minute later.
- **QA references drift across Verify runs.**
  - The same finding is Q1 in one entry and Q2 in the next, while Q5 names two different findings.
  - `qa@2026-11-04 20:10+08:00` calls the no-symbol case "driven live for the first time", but `qa@2026-11-04 19:47+08:00` already reports it at 99e4b4cc, with its Glob/Grep branch "covered in run 2".
  - It also says "4 in run 1" live samples, where that entry reports "5 parallel headless dispatches".
  - "Run N" means a QA pass inside one workflow in the first entry, and a whole verify-change run in the second.
- **What worked:**
  - Each claim of the joint design review was checked at file:line before acting (`review@2026-11-03 12:14+08:00`).
  - Assumptions were tested with live headless sessions at Criteria (calvin cycle 4).
  - Live CodeGraph use was efficient: one call answered B3.

## Takeaways

Each lesson becomes a check, a CLAUDE.md line or a skill edit, named here with its commit.

- **Run the owner's gates between plan and execution before the plan's exit check.** Both backward moves came from them -> skill edit: `plugins/pd/skills/planning/SKILL.md` step 5, prepend: "Before the exit check, run any gate the owner requires between plan and execution (calvin on plan.md, a simplification review) and apply its answers here; a gate run after `create-plan -> implement` costs a `(back)` move." Not a check: which gates apply is the owner's setting, outside pd. (commit: 3d10d53c)
- **A strict reply shape needs a machine consumer or a parser check.** Otherwise it is pinned only by wording -> skill edit: `plugins/pd/skills/designing/SKILL.md` `## Review checklist`, add: "- **Strict reply shapes have a parser:** a contract that pins an agent's reply as exact (the JSON object alone, a closed value set) names the code that parses it, or the Verify step that parses saved replies; with neither, pin it as its reader (the conductor) reads it." (commit: 3d10d53c)
- **Live replies carry the session's hooks too.** Find the source of unasked-for content before fixing it -> CLAUDE.md line, landed under `## Gotchas` (a one-line gotcha, not a guardrail with Why/Enforced/Stays): "**Live replies carry the session's hooks:** before fixing content a live agent reply carries that no agent instruction asks for, grep the stream's `hook_response` lines; the explorer's trailing 'Skipped: … Risk: …' lines followed a user-level SessionStart hook's end-of-reply rule, and three wording fixes treated the symptom." (commit: 3d10d53c)
- **A fix-cycle entry must land in the same commit as its edits** -> check: a pre-commit check that fails when a newly added log.md `review` entry says "revised" for shape.md or plan.md and the staged diff touches neither. This is real work, so it is a backlog line under Actions (filed in 3d10d53c).
- **QA references stay stable and figures are re-derived across Verify runs** -> agent edit: `plugins/pd/agents/qa-executor.md`, add: "A finding still open from an earlier `qa` entry cites it (`was qa@<ts>#Q<n>`); a fixed finding keeps its one-line claim beside its `Fixed:` line; a count restated from an earlier entry (live samples, branches driven) is re-read from that entry; say 'workflow run' or 'QA pass', never a bare 'run N'." Not a pd-lint check: "still open" is free text. (commit: 3d10d53c)

## Actions

- **Fix Q2 before close, or log it to the backlog.** In `plugins/pd/agents/codebase-explorer.md:75`, change "answered (returned results)" to "answered (results or a no-match answer)", and change C10's literal in `plugins/pd/scripts/test_explorer_codegraph.py` to match. If deferred: `pd-new backlog "codebase-explorer: an empty CodeGraph answer counts as answered (agent :75, plan C10 literal)"`.
- **Q4:** `pd-worktrees 2026-11-03-codebase-explorer-uses-codegraph --remove`, run by the conductor before close (the task-1 worktree under `.claude/worktrees/wf_3ee93b9c-a5f-1` was left after its merge).
- **Q3:** record a `note` that the diff touched `plugins/pd/README.md:67`, `docs/user-guide/installation.md` and `.claude/pd.local.md` outside shape.md `### Scope`, or update the Scope list before close.
- `pd-new backlog "codebase-explorer: check saved stream-json handbacks at Verify (whole-reply json.loads, search in the closed set, every source <path>:<line>, no skipped-item text in findings)"`. This covers Q6, and is the alternative to loosening the contract per the designing-checklist line above.
- `pd-new backlog "pre-commit: a log.md fix-cycle review entry naming shape.md or plan.md needs them in the same commit"`.
- `pd-new backlog "set source_paths/test_paths in .claude/pd.local.md so pd-lint --isolation covers this repository"` (this is `qa@2026-11-04 20:10+08:00#Q5`).
