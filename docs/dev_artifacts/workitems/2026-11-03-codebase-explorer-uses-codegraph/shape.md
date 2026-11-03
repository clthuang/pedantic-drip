# Shape: codebase-explorer uses CodeGraph

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- In a repository with a `.codegraph/` directory, `pd:codebase-explorer` asks CodeGraph first (`mcp__codegraph__codegraph_explore`), and falls back to Glob, Grep and Read when the repository has no index or CodeGraph is unavailable.
- A design or plan that renames something or moves a store carries the list of every surface it touches, with the query or command that produced it, so its reviewer can re-run that query and find a missed surface before code (folds backlog #078).

**Why:** the owner's global CLAUDE.md asks for CodeGraph before grep in every indexed repository, and pd's own research agent can't follow that rule today (`codebase-explorer.md:5` has `tools: [Glob, Grep, Read]`). Backlog #078 came from feature 124's retro (R1/A3, 2026-07-14, `docs/dev_artifacts/backlog-manual.md:202`): 9 catches across 15 review rounds were all incomplete enumerations of one table's consumers, each found by a finer literal sweep; the fix it names is to derive the surface from the call graph of the changed symbol, with literal grep as a supplementary net. Done looks like B3 and B7 holding on the next design that touches a rename.

### Non-goals

- Changing any reviewer's tools. The Claude reviewers stay pinned to Read, Grep and Glob (`validate.sh:399`); the review call goes to Codex first (`plugins/pd/references/review-call.md:15`), which can't call MCP tools, though it can run a shell command such as `codegraph explore` where it is installed. The reviewer re-runs the artifact's recorded query; it isn't told to use CodeGraph.
- Indexing a repository (`codegraph init`): that stays the user's decision.
- CodeGraph in other agents (`investigation-agent`, `rca-investigator`, `implementer`), and the `codegraph explore` CLI route (owner ruling 2026-11-03: no Bash in the explorer).
- `research-fanout`'s schema: on that path the workflow's `FINDINGS` schema (`research-fanout.js:25`, `claim`/`evidence`/`source`) replaces the agent's own output shape, and stays as it is.

### User stories

- As the conductor grounding a design (`designing` step 2), I get callers and call paths from one CodeGraph query through the explorer, instead of a dozen greps.
- As a reviewer of a rename's design or plan, I re-run the recorded query and compare its output with the surface list, so a missed caller is a blocker before code.

### Terms

- **Unavailable:** the tool is missing from the session, returns an error, times out, or answers that the repository has no index (an empty `.codegraph/` answers "CodeGraph isn't available here — no .codegraph/ index exists", checked 2026-11-03 with the CLI).
- **A search call:** a call to `mcp__codegraph__codegraph_explore`, Glob or Grep. A Read of a file the prompt names is not one.
- **`search`:** one added top-level field in the explorer's own output, one of: `codegraph` (CodeGraph answered and the findings rest on it, files read after it included), `codegraph, then grep` (CodeGraph answered but too little, so Glob and Grep followed), `grep` (no `.codegraph/`), `grep (codegraph unavailable: <reason>)`.
- **A store move:** moving where state lives: a file to another path, a config key to another file, a table to files. Its old name is the old path or key.
- **Surfaces:** callers, tests, fixtures, docs, config and CI that name the thing.

### Expectations

B1: `./validate.sh` on the repository -> passes, with `codebase-explorer` pinned as a role whose tools are exactly Glob, Grep, Read and `mcp__codegraph__codegraph_explore`.
B2: `validate.sh`'s agent-role fixture with `codebase-explorer.md`'s tools set to `[Glob, Grep, Read, Write]` -> `agent_roles_errors` prints one error line naming `codebase-explorer`, and the fixture's expected total becomes 9 (from 8, `validate.sh:427`).
B3: `pd:codebase-explorer` dispatched with the Agent tool in this repository (it has an index), with the `codegraph` MCP server connected, asked "who calls `switch_target`?" -> its transcript's first search call is `mcp__codegraph__codegraph_explore`; its output has `"search": "codegraph"` and a finding citing `plugins/pd/hooks/lib/commit_target.py:206` (the call inside `main()`).
B4: the same dispatch from a git repository with no `.codegraph/` -> no CodeGraph call in its transcript; `"search": "grep"`; findings with file:line.
B5: the same dispatch from a git repository whose `.codegraph/` is empty -> its output has `"search": "grep (codegraph unavailable: <reason>)"` and findings from Glob, Grep and Read.
B6: an explorer dispatch that finds nothing -> `findings: []` with a non-empty `no_findings_reason`, and a `search` value; never an error.
B7: the `designing` and `planning` skills' `## Review checklist` sections -> each has one line: a rename or store move lists its surfaces with the query or command that produced them (a `codegraph_explore` query when `.codegraph/` exists, else a grep for each old name), and the reviewer re-runs it; a surface in its output that the list lacks is a blocker.

B3 to B6 are live dispatches: the conductor runs them at Verify and records each transcript's path in the `qa` entry.

### Scope

- **In:** `plugins/pd/agents/codebase-explorer.md` (tools, search order, the `search` field, the fallback); `validate.sh` (`agent_roles_errors`, its fixture and the expected count); the two checklist lines; the CHANGELOG line.
- **Out:** reviewer tools; other agents; `research-fanout.js`; `codegraph init`; the agent's description, so `plugins/pd/README.md:67`, `README_FOR_DEV.md` and the architecture overview need no sync.

### Edge cases and must-nots

- **The server registered under another name** (another MCP server name, or from a plugin): the pinned tool name isn't in the session, so the explorer reports `grep (codegraph unavailable: tool not in session)`. The pin follows this machine's user-scope `codegraph` server (`~/.claude.json`, checked 2026-11-03).
- **A stale index:** CodeGraph's staleness banner names the stale files; the explorer reads those files directly, and the findings on them cite the file it read.
- **A query with no symbol in it** ("what testing conventions exist?"): CodeGraph is still asked once; too little back means `codegraph, then grep`.
- **Must not write:** the explorer never gets Write, Edit, Bash, or a tool that creates or rebuilds an index. `codegraph_explore` is a query; the server's own file watcher keeps the index in sync whether or not the explorer runs.
- **Must not fail without CodeGraph:** no dispatcher gets an error, or findings with no `no_findings_reason`, because CodeGraph is absent (B5, B6); that would break `designing` step 2 and `research-fanout` in every repository without an index.
- **Must not change the explorer's output fields** other than adding `search`: `findings[]` with `finding`, `source`, `relevance`, and `no_findings_reason` stay.
