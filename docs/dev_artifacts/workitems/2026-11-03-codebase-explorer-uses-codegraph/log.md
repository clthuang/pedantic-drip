<!-- Append-only history of 2026-11-03-codebase-explorer-uses-codegraph. Entry shapes: plugins/pd/references/log-entries.md. Example:
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."
-->

## 2026-11-03 11:02+08:00 note
Request (verbatim):
> pd:codebase-explorer uses CodeGraph when the repo has it: in a repo with a .codegraph/ directory, the agent queries codegraph (MCP codegraph_explore, else the codegraph explore CLI) before Glob/Grep/Read, and falls back to them without it Reviewers enumerate a rename's or store move's surfaces call graph first (folds #078).
Round request (user, 2026-11-03, verbatim):
> proceed to investigate, design and plan for three open backlog items in this round

## 2026-11-03 11:02+08:00 phase triage -> specify
Reason: small: two or three tasks, agent and reviewer markdown plus a validate check; existing agents to extend, no new module.

## 2026-11-03 11:08+08:00 decision
Q: when a repo has `.codegraph/` but the CodeGraph MCP tool is not connected, what should the explorer do (fall back to Grep, or add Bash to try the `codegraph explore` CLI)?
A (user, verbatim): "Fall back to Grep (Recommended)"

## 2026-11-03 11:12+08:00 review calvin cycle 1 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/calvin-cycle-1.md. Verdict: 9 blockers, 11 warnings, 4 notes; all 24 answered and `## Requirements` revised.
- R1 blocker shape.md:19 — two output shapes; `research-fanout`'s `FINDINGS` schema replaces the agent's own on that path (`research-fanout.js:25`, `:34`), now a non-goal, and B6's workflow-test claim is gone.
- R2 blocker shape.md:44 — where `search` shows: only in the explorer's own output, on Agent-tool dispatches (B3–B5).
- R3 blocker shape.md:30 — the reason lives inside the one `search` value.
- R4 blocker shape.md:30 — `search`'s four values defined, empty and stale answers included.
- R5 blocker shape.md:37 — one exact-set check, one fixture break, total 8 -> 9.
- R6 blocker shape.md:53 — the tool name follows the user-scope `codegraph` server (`~/.claude.json`, checked 2026-11-03); another name falls back with a reason.
- R7 blocker shape.md:44 — who runs B3–B6: the conductor at Verify, transcript paths in the `qa` entry; B5 reproduced with an empty `.codegraph/` (CLI answer checked 2026-11-03).
- R8 blocker shape.md:10 — who lists the surfaces: the artifact's author; the reviewer re-runs the recorded query.
- R9 blocker shape.md:42 — what counts as a rename's surface and its command; defined in Terms and B7.
To the user: none (rows 23 and 24, why this work, are answered from the owner's CLAUDE.md CodeGraph rule and #078's source, `backlog-manual.md:202`).
To the conductor (wording or consistency, each answered by a revision):
- rows 7, 9, 10, 11: `codegraph_explore` is a query; "search call" defined; B3 cites the call at `commit_target.py:206`; B6 rewritten (empty result, never an error).
- rows 13, 14, 15, 16, 17: query text stands as the command; store move and surfaces defined; "blast radius" and "complete" dropped.
- row 18: Codex can run a shell, so the non-goal now says reviewers re-run the recorded query rather than claiming Codex can't reach CodeGraph.
- rows 19, 20, 21, 22: empty report defined; "unavailable" defined once; the role pins tools only; the description stays, so no doc sync.

## 2026-11-03 11:21+08:00 review calvin cycle 2 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/calvin-cycle-2.md. Verdict: 3 blockers, 8 warnings, 8 notes; cycle 1: 22 rows answered, rows 21 and 24 partly, both now answered (role `explorer`, tools only; greps always beside the call graph). All 19 answered and `## Requirements` revised.
Closes: review@2026-11-03 11:12+08:00#R1, review@2026-11-03 11:12+08:00#R2, review@2026-11-03 11:12+08:00#R3, review@2026-11-03 11:12+08:00#R4, review@2026-11-03 11:12+08:00#R5, review@2026-11-03 11:12+08:00#R6, review@2026-11-03 11:12+08:00#R7, review@2026-11-03 11:12+08:00#R8, review@2026-11-03 11:12+08:00#R9
- R1 blocker shape.md:43 — how a reviewer re-runs a CodeGraph query; it re-runs what its tools allow (Codex's shell can run `codegraph explore`), and the greps always.
- R2 blocker shape.md:28 — how the explorer checks for `.codegraph/`; it doesn't: it always asks CodeGraph first and the tool's own "no index" answer decides (B4).
- R3 blocker shape.md:40 — dispatching from another repository; a headless `claude -p --plugin-dir plugins/pd` session in a scratch repository under `agent_sandbox/` (B4, B5).
To the user: none.
To the conductor (wording or consistency, each answered by a revision):
- rows 4, 5, 15, 16: greps always run beside the call-graph query (#078's supplementary net), which covers string-named consumers; a table's old name is its name; the missed-by-both case is out.
- rows 6, 9, 10, 11, 12, 18, 19: "done" reworded; B3 cites the call line as it is at Verify; B6 names its query and pre-check; `search` read off the transcript; a missing tool wins; an unconnected server makes B3 not run and asks the user; an unnamed Read is a search call.
- rows 7, 8, 13, 14, 17: B1 runs under two locales; role `explorer` pins tools only; B5 checks a dispatch runs without the tool; a frozen index is a stale index; the CHANGELOG line named.

## 2026-11-03 11:29+08:00 review calvin cycle 3 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/calvin-cycle-3.md. Verdict: 3 blockers, 4 warnings, 7 notes; cycle 2: 18 rows answered, row 5 partly (what the call-graph half is checked against), now answered by B7. This is the third cycle: the cap.
Closes: review@2026-11-03 11:21+08:00#R1, review@2026-11-03 11:21+08:00#R2, review@2026-11-03 11:21+08:00#R3
- R1 blocker shape.md:42 — the made-up name sat in the spec, so the grep pre-check would find the spec; B6 now has the conductor make the name up at Verify.
- R2 blocker shape.md:39 — an Agent-tool dispatch loads the installed release's agent; B3 now runs headless with `--plugin-dir` at the work tree's absolute path.
- R3 blocker shape.md:40 — a scratch repository under `agent_sandbox/` sits under this repository's index; B4 now uses `mktemp -d` outside it, with `--plugin-dir` absolute.
To the user: whether this revision ends the loop (the cap question).
To the conductor (each answered by the same revision):
- rows 4, 5: `app.py` has `run()` calling `main()`; the reason is one of four fixed strings.
- rows 6, 7: the artifact records commands and hits, each hit a surface or history; Claude reviewers re-run the greps and check the recorded call-graph hits.
- rows 8, 9, 14: the explorer writes `search`, the transcript wins at Verify; the transcript is the stream-json messages under the explorer's `parent_tool_use_id`; `search` tells a dispatcher whether call paths were followed.
- rows 10, 11, 12, 13: no change beyond "Done" now meaning B1 to B7 at Verify; Codex runs the CLI where its sandbox allows, else the greps; CI's Ubuntu run is the second machine; the checklist line names what the artifact carries.

## 2026-11-03 11:29+08:00 capped specify
Deferred: none
Follow-ups: none
Decisions:
- whether the revision answering cycle 3's blockers ends the calvin loop, or a fourth cycle runs: asked of the user.
Assumptions:
- A1: `claude -p --output-format stream-json --verbose` carries a subagent's messages with its dispatch's `parent_tool_use_id` (checked at Verify; if not, the transcript is the session's subagent file under `~/.claude/projects/`).
Closes: review@2026-11-03 11:29+08:00#R1, review@2026-11-03 11:29+08:00#R2, review@2026-11-03 11:29+08:00#R3

## 2026-11-03 11:31+08:00 decision
Q: does the revision answering calvin cycle 3 end the calvin loop?
A (user, verbatim): "Run a 4th calvin cycle"
answers: capped@2026-11-03 11:29+08:00
Sign-off asked in the same question set; the user answered "wait for 4th calvin cycle", so it stays open.

## 2026-11-03 12:05+08:00 review calvin cycle 4 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/calvin-cycle-4.md (the owner's extra cycle, decision@2026-11-03 11:31+08:00). Verdict: 1 blocker, 7 warnings, 10 notes; cycle 3: 9 rows answered, 2 partly (2, 14), 3 open (10, 11, 13); all now answered. Three assumptions were probed with headless sessions on 2026-11-03 instead of argued.
Closes: capped@2026-11-03 11:29+08:00#A1
- R1 blocker shape.md:28 — the no-index answer was checked only with the CLI; the MCP tool's own answer in an unindexed scratch repository is now quoted (headless session, server connected), and `no index` covers any answer saying no `.codegraph/` was found.
To the user: whether this cycle ends the loop, and the sign-off.
To the conductor (each answered by a revision):
- rows 2, 3: B4 needs the server too; not-connected keeps the work item in Verify and asks the user.
- rows 4, 5, 16: probed: stream-json carries the explorer's tool calls under its dispatch's `parent_tool_use_id` (closes A1); a marked `--plugin-dir` copy loaded over the installed release; `--strict-mcp-config` with no config starts.
- rows 6, 7, 8, 9: streams written outside the repository during the run; B6 passes when no finding locates the name, and needs `search` starting with `codegraph`; B6 is a new session.
- rows 10, 11, 17: the reviewer re-runs the greps and the query where its tools allow, and checks recorded hits; history is a closed list, everything else is a surface; B7 stays a line check.
- rows 12, 14, 15, 18: timeout folds into `error: <line>`; `app.py` defines `main()`; "above" is up to `/`; any answered call counts.
- row 13 and cycle-3 rows 10, 11, 13: `search` serves the designing-step-2 dispatcher, not research-fanout; Codex falls back to the greps; B1 also runs in CI's validate step; the checklist is the author's bar too (`designing/SKILL.md:14`, `planning/SKILL.md:13`).

## 2026-11-03 12:05+08:00 decision
Q: does calvin cycle 4, answered, end the calvin loop?
A (user, verbatim): "End the loop (Recommended)"
answers: capped@2026-11-03 11:29+08:00

## 2026-11-03 12:05+08:00 decision-2
Q: criteria signed off?
A (user, verbatim): "Signed off"

## 2026-11-03 12:05+08:00 phase specify -> design
Criteria signed off (decision above); calvin loop ended by the owner after cycle 4.

## 2026-11-03 12:08+08:00 note
Grounding: the conductor read plugins/pd/agents/codebase-explorer.md in full, validate.sh:385-429 (agent_roles_errors and its fixture), and both skills' review checklists this session; no codebase-explorer dispatch, since the explorer is the thing changing and its report would restate that read.

## 2026-11-03 12:14+08:00 review joint design and plan — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, on commit a4c70fb3 (brief agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/review-brief-1.md). Verdict: not approved; 3 blockers. Each claim checked at file:line before acting; all three hold.
- R1 blocker shape.md: — ExplorerDispatch gave one output shape though research-fanout supplies its own FINDINGS schema (`research-fanout.js:25`, passed at `:34`); the contract now has the supplied-schema branch, `search` not carried, and C11 pins it.
- R2 blocker plan.md: — no case for the symbol-free query or the several-calls rule; SearchOrder now states both, and C10 pins them in the agent text.
- R3 blocker plan.md:26 — C6 checked field presence, weaker than "search is the only change"; it now asserts the exact key sets of both examples.
Fix cycle 1 of 3: shape.md `## Design` and plan.md revised; pd-lint and `phase-gate.sh design` pass. Next: a scoped re-review.

## 2026-11-03 12:15+08:00 note
Correction to review@2026-11-03 12:14+08:00: its commit (97e8cdf6) recorded fix cycle 1 as applied, but the edit script had stopped at its first check and changed nothing. The edits it describes land in the commit carrying this note; pd-lint and `phase-gate.sh design` were re-run on them and pass.

## 2026-11-03 12:19+08:00 review joint design and plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, scoped to R1 to R3 and the edit a4c70fb3..5bbb5e07 (brief agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/review-brief-2.md). R1, R2 and R3 resolved; nothing new in the diff. The loop ends: a pass with no blocker.
Closes: review@2026-11-03 12:14+08:00#R1, review@2026-11-03 12:14+08:00#R2, review@2026-11-03 12:14+08:00#R3

## 2026-11-03 12:19+08:00 phase design -> create-plan
Small mode: the joint review covered the design and the plan; its loop ended with no blocker (review above).

## 2026-11-03 12:19+08:00 phase-2 create-plan -> implement
Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 12:19+08:00 note
Goal-run offer skipped: the owner scoped this round to investigate, design and plan the three backlog items, with no Execute ("proceed to investigate, design and plan for three open backlog items in this round").

## 2026-11-03 18:56+08:00 review plan, simplification — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, a simplification review of shape.md ## Design and plan.md at ef9ca47b (the owner's ask: "use agents to code review, QA, and simplify implementation without compromising functionality"; brief agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/simplify-brief-1.md). Approved; one marginal cut, no blocker.
- R1 note plan.md:21 — drop C1's two direct `roles()` calls on the real agents directory: C2 already runs that check through `validate.sh` under both locales (`validate.sh:415` logs every `agent_roles_errors` line through `log_error`, which counts it, `validate.sh:15-18`). C1 keeps its exact frontmatter assertion; C3 and C4 keep the direct calls on the copy.

## 2026-11-03 18:56+08:00 phase implement -> create-plan (back)
Reason: the simplification review above (R1). Nothing has executed.
Invalidates: plan.md C1.

## 2026-11-03 19:01+08:00 review plan, scoped — codex
Reviewer: codex:codex-rescue, gpt-6-astra at xhigh, the QA pass on the simplification ef9ca47b..5170371d (brief agent_sandbox/2026-11-03/2026-11-03-codebase-explorer-uses-codegraph/simplify-qa-brief-1.md). Approved, no issues: C1 still pins the explorer's exact tools, C2 runs the removed roles check through `validate.sh` under both locales (validate.sh:415, :15-18, :747-752), C3 and C4 unchanged; no earlier finding reopened.

## 2026-11-03 19:01+08:00 phase create-plan -> implement
Simplification applied and QA-approved (review above). Plan exit check passed (phase-gate.sh create-plan, pd-lint clean).

## 2026-11-03 19:23+08:00 phase implement -> design (back)
Reason: calvin on plan.md, the owner's rule between plan and execution (32 questions, the conductor adjudicating as author). Two answers change ## Design: RenameChecklistLine lacks three parts of B7, and SearchOrder leaves the agent's `## Search Strategies` and its "Read files without searching first" must-not describing a search with no CodeGraph. Nothing has executed.
Invalidates: shape.md ## Design (RenameChecklistLine, SearchOrder); plan.md.

## 2026-11-03 19:24+08:00 note
Calvin on plan.md (the owner's rule before Execute): one pass in report mode, 32 questions, adjudicated by the conductor as the plan's author; 22 fixed, 8 answered, 2 dismissed. Fixed:
- ## Design: RenameChecklistLine gains B7's three missing parts (anything else, the open backlog and `[Unreleased]` included, is a surface; each hit checked at file:line; a disputed mark is a finding); SearchOrder carries the agent's own definition of unavailable (a timeout included); a SearchStrategies clause puts the CodeGraph query first in `## Search Strategies` and rewrites the must-not "Read files without searching first" to count a CodeGraph call.
- plan.md: shared terms define a section, `agents_copy` and what a tag means; each text case names the literal substrings it checks (C5, C7, C10, C11); C1 compares tools as a set; C2 also checks `validate.sh` no longer says 8; C3 gains a half true only once the explorer role exists (the red-first proof); C4's second line pinned; C6 pins the two examples' `relevance` and `search` values; C8's literal comes from shape.md; C9 checks the CHANGELOG line.
Answered: `validate.sh` exits 0 under both locales today (checked); `en_US.UTF-8` exists here and on macOS runners; C2 covers B1's CI clause by running the same script; the text cases catch a missing instruction at the merger's proof, before Verify's live runs; the case order carries nothing; the checklist lines share Task 1 (KISS).
Dismissed: pinning model, description and color in a permanent test (a changed value shows in the branch diff at Verify); a separate order requirement for C1 (covered by the set comparison).

## 2026-11-03 19:24+08:00 phase design -> create-plan
Calvin's Design fixes applied (note above); design exit check passed.

## 2026-11-03 19:24+08:00 phase-2 create-plan -> implement
Plan exit check passed (phase-gate.sh create-plan, pd-lint clean); from_shape matches shape.md.

## 2026-11-03 19:32+08:00 run implement-tasks — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 2. Tokens: 16781. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_3ee93b9c-a5f/journal.jsonl
Commit: fe331ca9
- task 1: merged, proof pass, cycles 0, branch pd/2026-11-03-codebase-explorer-uses-codegraph/task-1
  case_map: C1=plugins/pd/scripts/test_explorer_codegraph.py::test_c1_explorer_tools_are_exactly_the_four, C2=plugins/pd/scripts/test_explorer_codegraph.py::test_c2_validate_passes_with_nine_fixture_checks[C] plugins/pd/scripts/test_explorer_codegraph.py::test_c2_validate_passes_with_nine_fixture_checks[en_US.UTF-8] plugins/pd/scripts/test_explorer_codegraph.py::test_c2_validate_holds_no_stale_eight, C3=plugins/pd/scripts/test_explorer_codegraph.py::test_c3_tool_order_and_locale_do_not_matter, C4=plugins/pd/scripts/test_explorer_codegraph.py::test_c4_explorer_role_rejects_write_and_the_old_list, C5=plugins/pd/scripts/test_explorer_codegraph.py::test_c5_research_process_asks_codegraph_first, C6=plugins/pd/scripts/test_explorer_codegraph.py::test_c6_output_examples_gain_only_search, C7=plugins/pd/scripts/test_explorer_codegraph.py::test_c7_stale_index_rule, C8=plugins/pd/scripts/test_explorer_codegraph.py::test_c8_rename_checklist_line[designing] plugins/pd/scripts/test_explorer_codegraph.py::test_c8_rename_checklist_line[planning], C9=plugins/pd/scripts/test_explorer_codegraph.py::test_c9_ci_and_changelog, C10=plugins/pd/scripts/test_explorer_codegraph.py::test_c10_no_symbol_query_and_several_calls, C11=plugins/pd/scripts/test_explorer_codegraph.py::test_c11_own_output_shape_leaves_out_search; greens: none; skipped: none

## 2026-11-03 19:33+08:00 phase implement -> verify
Implement exit check passed (phase-gate.sh implement: every plan task on a merged, proof pass line). Proving tests re-run on the branch after the merge: 14 passed.

## 2026-11-04 19:22+08:00 note
Live B3 to B6, driven by the conductor at 3f0142f0 (claude 2.1.318, `claude -p --plugin-dir /Users/terry/projects/pedantic-drip/plugins/pd --output-format stream-json --verbose < /dev/null`, streams written to the session scratchpad while running, copied to agent_sandbox/2026-11-04/2026-11-03-codebase-explorer-uses-codegraph/live/b3.jsonl to b6.jsonl). The explorer's calls are the stream messages carrying the dispatch's `parent_tool_use_id`, so A1 holds.
- B3 holds: cwd this repository, `codegraph` connected; first call `mcp__codegraph__codegraph_explore` ("switch_target callers"); `"search": "codegraph"`; finding cites `plugins/pd/hooks/lib/commit_target.py:206` (the `switch_target(` call in `main()`, :163).
- B4 holds: cwd a `mktemp -d` git repository (no `.codegraph/` in it or above it, checked) holding `app.py` (`main()` :1, `run()` calling it :6); first call CodeGraph, which answered "isn't indexed with codegraph (no .codegraph/ directory found ...)"; `"search": "grep (codegraph unavailable: no index)"`; finding cites `app.py:6`.
- B5 holds: as B4 with `--strict-mcp-config` and no config (init lists no MCP server); `"search": "grep (codegraph unavailable: tool not in session)"`; finding cites `app.py:6`.
- B6 holds: `QuillarbFrobnicator` (`grep -rn` over the repository: 0 hits before the run); `"findings": []` with a non-empty `no_findings_reason`; `"search": "codegraph, then grep"`; `is_error: false`.

## 2026-11-04 19:47+08:00 run verify-change — finished
Session: 9ff7243d-736c-40dd-a44c-1f533b1cce4a  Agents: 6. Tokens: 47823. Cycles: 2. Journal: ~/.claude/projects/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/subagents/workflows/wf_6b75b6cd-7ed/journal.jsonl
Run: wf_6b75b6cd-7ed. Stopped: none.

## 2026-11-04 19:47+08:00 review verify — codex (fallback: no)
Verdict: changes requested. Commit: 1feb0559. The review confirms review@2026-11-03 12:05+08:00#R1's open claim from the saved B4 stream (the MCP tool's own no-index answer).
- R1 blocker plugins/pd/agents/codebase-explorer.md:76 — The default explorer response violates ExplorerDispatch's single-JSON-object contract. Require JSON-only output and validate the complete explorer handback, including trailing content.
Closes: review@2026-11-03 12:05+08:00#R1

## 2026-11-04 19:47+08:00 qa
Commit: 99e4b4cc
Ran: `./validate.sh` -> pass
Ran: `bash plugins/pd/hooks/tests/test-hooks.sh` -> pass
Ran: `bash scripts/test-release.sh` -> pass
Ran: `bash -ec 'for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done'` -> pass
Ran: `bash -ec 'for s in pd-adopt pd-init pd-lint pd-new pd-proof pd-review-filter pd-status; do "plugins/pd/scripts/$s" --self-test; done'` -> pass
Ran: `python3 plugins/pd/scripts/pd_common.py --self-test` -> pass
Ran: `uv run --script plugins/pd/scripts/pd-html.py --self-test` -> pass
Ran: `node plugins/pd/workflows/tests/test-workflows.mjs` -> pass
Ran: `uv run --project plugins/pd pytest -q plugins/pd` -> pass
Criteria gaps: B3 to B6 driven live by the conductor at 3f0142f0, all holding (note@2026-11-04 19:22+08:00; streams agent_sandbox/2026-11-04/2026-11-03-codebase-explorer-uses-codegraph/live/b3.jsonl to b6.jsonl), and re-driven by QA at 99e4b4cc (below).
Criteria gaps: Q2 fix check, mechanical part: test_c12_reply_carries_no_code_fence fails at 951583ee (1 failed, 15 passed, in a detached worktree I removed afterwards) and passes at 99e4b4cc (16 passed). So the red-then-green proof holds. Like R1's test, C12 checks only the instruction text. No test parses a real reply, so the behaviour is covered only by the live samples below.
Criteria gaps: Q2 live behaviour, re-driven at 99e4b4cc. There were 5 parallel headless dispatches (claude -p --plugin-dir plugins/pd --output-format stream-json --verbose): B3, B4, B5 (--strict-mcp-config), B6 (with the fresh name Quorvintalex40417, 0 grep -rn hits before the run) and the no-symbol query. Every handback passed a strict json.loads of the whole dedented report. None was fenced and none had trailing prose. Streams and handbacks are under /private/tmp/claude-501/-Users-terry-projects-pedantic-drip/9ff7243d-736c-40dd-a44c-1f533b1cce4a/scratchpad/qa3/ (*.jsonl, *.toolresult). This is one nondeterministic sample per case. The streams were not copied under agent_sandbox/, because QA fixes nothing.
Criteria gaps: B1: CI's validate step (ci.yml:23) was not watched at 99e4b4cc. Only the local default-locale run was seen directly. C2 covers LC_ALL=C and en_US.UTF-8.
Criteria gaps: B2: validate.sh still checks only the fixture's total error count (9). A role that printed two lines could hide a missing codebase-explorer line. C4 pins that line through a direct agent_roles_errors call.
Criteria gaps: B3 at HEAD: the only call was codegraph_explore('switch_target callers') with no projectPath, and search='codegraph'. One finding cites commit_target.py:206, the switch_target( call inside main() (def at :163, no other def between). It holds, but the finding was cited from CodeGraph's output without a Read. Another finding cites :131, the def itself, not a caller. The stale-index rule (SearchOrder step 4) was never exercised live.
Criteria gaps: B4 at HEAD: CodeGraph was called first, with projectPath passed explicitly to the scratch repo, and answered no index. Grep and Read followed, search='grep (codegraph unavailable: no index)', and the finding was app.py:6. Before the run I checked the scratch repo and every directory above it for .codegraph/ and found none. Because projectPath was passed explicitly, B4 still does not show that the server defaults to the session's project directory.
Criteria gaps: B5 at HEAD: init lists no MCP servers, and the explorer made no CodeGraph call. It ran Grep, Glob and Read, wrote search='grep (codegraph unavailable: tool not in session)', and found app.py:6. It holds. The 'error: <first line>' reason and the 'server registered under another name' edge case were never driven live; only C5 and C10 pin their text.
Criteria gaps: B6 at HEAD: codegraph_explore returned 'No relevant code found for "Quorvintalex40417"', then Grep ran. findings=[] with a non-empty no_findings_reason, search='codegraph, then grep', and no error. It holds only by reading the empty answer as 'answered' (Q1).
Criteria gaps: No-symbol edge case at HEAD: codegraph_explore('what testing conventions exist?') was asked once as written. No Glob or Grep followed, and search='codegraph' matches the transcript. The Glob/Grep branch of this edge case was covered in run 2, not here.
Criteria gaps: B7: C8 checks that the checklist line appears verbatim in both skills. No rename or store move has gone through the line yet, so no reviewer has applied it.
Criteria gaps: research-fanout path (schema supplied, search left out): not driven live. Only C11 pins the text, and test-workflows.mjs uses stubbed agents.
Criteria gaps: The battery ran at the same time as the 5 live sessions. All 9 commands exited 0, with Validation passed and 0 warnings. pytest over plugins/pd collected 26 tests, 16 of them from test_explorer_codegraph.py.
Criteria gaps: pd-lint on the work-item directory: exit 0. Isolation lint was not re-run; in run 2 it skipped itself because no source_paths/test_paths are set.
- Q1 note plugins/pd/agents/codebase-explorer.md:74 — Step 3 still counts a CodeGraph call only when it 'answered (returned results)'. An empty answer ('No relevant code found') is neither results nor one of the three unavailable reasons, so it has no allowed `search` value. B6 depends on the explorer reading it as answered.
- Q3 note plugins/pd/README.md:67 — The diff still touches files that shape.md ## Scope lists as Out or does not list: plugins/pd/README.md:67, docs/user-guide/installation.md and .claude/pd.local.md. shape.md was not updated to match.
- Q4 note .claude/worktrees/wf_3ee93b9c-a5f-1:0 — This work item's task worktree is still present after its merge. Under CLAUDE.md, implementing step 5 removes task worktrees with pd-worktrees <id> --remove.
- Q5 warning plugins/pd/agents/codebase-explorer.md:67 — Line 67 (the R1/Q2 output line) sends anything skipped or unchecked to 'no_findings_reason or a finding'. A finding about something not checked has no file to cite, so the explorer writes a source that breaks the pinned contract `"source": "<path>:<line>"` (shape.md ExplorerDispatch). No test checks the source format of a real reply.
Fixed: R1 by 669643b6 — plugins/pd/scripts/test_explorer_codegraph.py::test_c12_reply_is_the_json_object_alone (failed before the fix, committed in edb60e6c)
Fixed: Q2 by 99e4b4cc — plugins/pd/scripts/test_explorer_codegraph.py::test_c12_reply_carries_no_code_fence (failed before the fix, committed in 951583ee)
Closes: review@2026-11-04 19:47+08:00#R1

## 2026-11-04 19:54+08:00 decision
Q: qa@2026-11-04 19:47+08:00#Q5 (warning: codebase-explorer.md:67 sends skipped items to `no_findings_reason` "or a finding", and a finding must cite `<path>:<line>`): fix it or backlog it?
A (user, verbatim): "Re-run Verify to fix it (Recommended)"
