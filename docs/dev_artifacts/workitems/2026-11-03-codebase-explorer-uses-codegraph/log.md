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
