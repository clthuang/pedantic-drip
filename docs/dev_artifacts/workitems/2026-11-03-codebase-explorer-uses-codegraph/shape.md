# Shape: codebase-explorer uses CodeGraph

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- In a repository with a `.codegraph/` directory, `pd:codebase-explorer` asks CodeGraph first (`mcp__codegraph__codegraph_explore`), and falls back to Glob, Grep and Read when the repository has no index or the tool isn't available.
- A rename or a store move is reviewed against every surface it touches, listed callers first from the call graph, not only the files the change happens to name (folds backlog #078).

### Non-goals

- Reviewers running CodeGraph themselves. The review call goes to Codex first (`plugins/pd/references/review-call.md:15`), which can't call MCP tools, and the Claude reviewers' tools are pinned to Read, Grep and Glob (`validate.sh:399`). The reviewer checks the enumeration the artifact carries instead.
- Indexing a repository (`codegraph init`): that stays the user's decision.
- CodeGraph in other agents (`investigation-agent`, `rca-investigator`, `implementer`).

### User stories

- As the conductor grounding a design (`designing` step 2), I get the explorer's callers and blast radius from one CodeGraph query, so the design's caller list is complete without a dozen greps.
- As a reviewer of a rename's design or plan, I can check its surface list against how it was enumerated, so a missed caller is a blocker before code.

### Expectations

B1: `./validate.sh` on the repository -> passes, with `codebase-explorer` pinned as a role: its tools are Read, Grep, Glob and `mcp__codegraph__codegraph_explore`, and nothing that writes.
B2: `validate.sh`'s agent-role fixture with a `codebase-explorer.md` whose tools lack `mcp__codegraph__codegraph_explore`, or add Write or Edit -> one error line naming `codebase-explorer` for each.
B3: `pd:codebase-explorer` dispatched in this repository (it has `.codegraph/`) with the CodeGraph MCP server connected, asked "who calls `switch_target`?" -> its transcript's first search call is `mcp__codegraph__codegraph_explore`; its report says `search: codegraph` and cites `plugins/pd/hooks/lib/commit_target.py` with a line number.
B4: the same dispatch in a repository with no `.codegraph/` -> its transcript has no CodeGraph call; its report says `search: grep` and still returns findings with file:line.
B5: `.codegraph/` present but the tool missing from the session or returning an error -> the agent falls back to Glob, Grep and Read; its report says `search: grep` and gives the reason (`codegraph unavailable: <reason>`).
B6: `plugins/pd/workflows/tests/test-workflows.mjs` -> passes unchanged (`research-fanout` still gets its `FINDINGS` shape from the explorer).
B7: the `designing` and `planning` skills' `## Review checklist` sections -> each has one line requiring a rename or a store move to list every surface it touches (callers, tests, docs, config), enumerated callers first from the call graph (CodeGraph when `.codegraph/` exists, else a grep for each old name), with the command that produced the list.

### Scope

- **In:** `plugins/pd/agents/codebase-explorer.md` (tools, search order, the `search:` field, the fallback); `validate.sh` (`agent_roles_errors` and its fixture count); the two checklist lines; the CHANGELOG line; `plugins/pd/README.md`'s agent row if its description changes.
- **Out:** the `codegraph explore` CLI fallback, unless the owner rules it in (it needs Bash in a read-only agent; see the sign-off question); reviewer tools; other agents; `codegraph init`.

### Edge cases and must-nots

- **`.codegraph/` present, index stale:** CodeGraph's own staleness banner names the stale files; the explorer reads those files directly and says so in the finding.
- **A query with no symbol in it** ("what testing conventions exist?"): CodeGraph is still asked once; an empty answer is not a failure, and the explorer goes on with Glob and Grep.
- **Must not write:** the explorer never gets Write, Edit, or a tool that creates or rebuilds an index, so research stays read-only.
- **Must not fail without CodeGraph:** no dispatcher may get an error or an empty report because CodeGraph is absent; that would break `research-fanout` and `designing` in every repository without an index.
- **Must not change the output shape** dispatchers read: `findings[]` with `finding`, `source`, `relevance`, and `no_findings_reason`; `search` is one added top-level field.
