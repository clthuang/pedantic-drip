# Shape: codebase-explorer uses CodeGraph

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- `pd:codebase-explorer` asks CodeGraph first (`mcp__codegraph__codegraph_explore`) and falls back to Glob, Grep and Read when CodeGraph is unavailable, including in a repository with no index.
- A design or plan that renames something or moves a store carries the list of every surface it touches, built from a call-graph query plus a grep for each old name, with both recorded, so its reviewer can re-run them and find a missed surface before code (folds backlog #078).

**Why:** the owner's global CLAUDE.md asks for CodeGraph before grep in every indexed repository, and pd's own research agent can't follow that rule today (`codebase-explorer.md:5` has `tools: [Glob, Grep, Read]`). Backlog #078 came from feature 124's retro (R1/A3, 2026-07-14, `docs/dev_artifacts/backlog-manual.md:202`): 9 catches across 15 review rounds were all incomplete enumerations of one table's consumers, each found by a finer literal sweep; the fix it names is to derive the surface from the call graph of the changed symbol, with literal grep as a supplementary net. Done looks like B3 to B6 holding at Verify, and B7's line applied by the next review of a rename.

### Non-goals

- Changing any reviewer's tools. The Claude reviewers stay pinned to Read, Grep and Glob (`validate.sh:399`). The review call goes to Codex first (`plugins/pd/references/review-call.md:15`); Codex can't call MCP tools but has a shell, so it can run the `codegraph explore` CLI where it is installed.
- Indexing a repository (`codegraph init`): that stays the user's decision.
- CodeGraph in other agents (`investigation-agent`, `rca-investigator`, `implementer`), and the `codegraph explore` CLI route in the explorer (owner ruling `decision@2026-11-03 11:08+08:00`: "Fall back to Grep (Recommended)", no Bash in the explorer).
- `research-fanout`'s schema: on that path the workflow's `FINDINGS` schema (`research-fanout.js:25`, `claim`/`evidence`/`source`) replaces the agent's own output shape, and stays as it is.

### User stories

- As the conductor grounding a design (`designing` step 2), I get callers and call paths from one CodeGraph query through the explorer, instead of a dozen greps.
- As a reviewer of a rename's design or plan, I re-run the recorded query and greps and compare their output with the surface list, so a missed caller is a blocker before code.

### Terms

- **Unavailable:** the tool is missing from the session, returns an error, times out, or answers that the repository has no index (an empty or absent `.codegraph/` answers "CodeGraph isn't available here — no .codegraph/ index exists", checked 2026-11-03 with the CLI). When the tool is missing, that is the reason given, whatever the repository holds.
- **A search call:** a call to `mcp__codegraph__codegraph_explore`, Glob or Grep, or a Read of a file the prompt doesn't name.
- **`search`:** one added top-level field in the explorer's own output, read off its transcript: `codegraph` (a CodeGraph call answered, and no Glob or Grep follows it), `codegraph, then grep` (a CodeGraph call answered, and a Glob or Grep follows it), or `grep (codegraph unavailable: <reason>)`.
- **A stale index:** CodeGraph's banner names stale files, or says auto-sync is disabled (the whole index frozen). Either way the explorer reads each file a finding rests on before citing it.
- **A store move:** moving where state lives: a file to another path, a config key to another file, a table to files. Its old name is the old path, key or table name.
- **Surfaces:** callers, tests, fixtures, docs, config and CI that name the thing or reach it through a call path.

### Expectations

B1: `./validate.sh` on the repository, under `LC_ALL=C` and under `LC_ALL=en_US.UTF-8` -> passes both times, with `codebase-explorer` pinned in role `explorer` (tools only) to exactly Glob, Grep, Read and `mcp__codegraph__codegraph_explore`.
B2: `validate.sh`'s agent-role fixture with `codebase-explorer.md`'s tools set to `[Glob, Grep, Read, Write]` -> `agent_roles_errors` prints one error line naming `codebase-explorer`, and the fixture's expected total becomes 9 (from 8, `validate.sh:427`).
B3: `pd:codebase-explorer` dispatched with the Agent tool in this repository (it has an index), the `codegraph` MCP server connected, asked "who calls `switch_target`?" -> its transcript's first search call is `mcp__codegraph__codegraph_explore`; its output's `search` starts with `codegraph`, and a finding cites `plugins/pd/hooks/lib/commit_target.py` at the line of the `switch_target(` call inside `main()` as it is at Verify.
B4: a headless session (`claude -p --plugin-dir plugins/pd`) started in a scratch git repository with no `.codegraph/` and one Python file, dispatching the explorer with "who calls `main`?" -> its first search call is the CodeGraph call, which answers no index; `"search": "grep (codegraph unavailable: no index)"`; findings with file:line.
B5: the same as B4, with MCP servers turned off (`--strict-mcp-config`, no config) -> the dispatch runs; `"search": "grep (codegraph unavailable: tool not in session)"`; findings with file:line.
B6: the explorer asked in this repository "where is `FrobnicatorFactory` defined?" (checked first: `grep -rn FrobnicatorFactory` finds nothing) -> `findings: []` with a non-empty `no_findings_reason` and a `search` value; no error.
B7: the `designing` and `planning` skills' `## Review checklist` sections -> each has one line: a rename or store move lists its surfaces, built from a call-graph query (`codegraph_explore` or `codegraph explore`, when `.codegraph/` exists) plus a grep for each old name, with the query and greps recorded; the reviewer re-runs what its tools allow (the greps always), and a surface in their output that the list lacks is a blocker.

The conductor runs B3 to B6 at Verify, records each transcript's path in the `qa` entry, and makes the scratch repositories under `agent_sandbox/`. If the `codegraph` server isn't connected at Verify, B3 is recorded as not run and the user is asked.

### Scope

- **In:** `plugins/pd/agents/codebase-explorer.md` (tools, search order, the `search` field, the fallback); `validate.sh` (`agent_roles_errors`, its fixture and the expected count); the two checklist lines; one `CHANGELOG.md` `[Unreleased]` line saying the explorer asks CodeGraph first and renames record their enumeration.
- **Out:** reviewer tools; other agents; `research-fanout.js`; `codegraph init`; the agent's description, so `plugins/pd/README.md:67`, `README_FOR_DEV.md` and the architecture overview need no sync.

### Edge cases and must-nots

- **The server registered under another name** (another MCP server name, or from a plugin): the pinned tool name isn't in the session, so the explorer reports `grep (codegraph unavailable: tool not in session)`. The pin follows this machine's user-scope `codegraph` server (`~/.claude.json`, checked 2026-11-03).
- **Which index the server answers about:** the session's project directory; B4 shows it, since an answer about another repository's index would fail B4.
- **A query with no symbol in it** ("what testing conventions exist?"): CodeGraph is still asked once; Glob or Grep after it makes `codegraph, then grep`.
- **A caller both the query and the greps miss** (reached only through a string the greps didn't name): outside this work item; the review checklists' other lines still apply.
- **Must not write:** the explorer never gets Write, Edit, Bash, or a tool that creates or rebuilds an index. `codegraph_explore` is a query; the server's own file watcher keeps the index in sync whether or not the explorer runs.
- **Must not fail without CodeGraph:** no dispatcher gets an error, or findings with no `no_findings_reason`, because CodeGraph is absent (B4, B5, B6); that would break `designing` step 2 and `research-fanout` in every repository without an index.
- **Must not change the explorer's output fields** other than adding `search`: `findings[]` with `finding`, `source`, `relevance`, and `no_findings_reason` stay.
