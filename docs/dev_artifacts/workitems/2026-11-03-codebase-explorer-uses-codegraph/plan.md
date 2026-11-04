---
from_shape: 92e1581a68fb4e8a01f98761305892013e6493f1
---
# Plan: codebase-explorer uses CodeGraph

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

Shared terms: `roles(dir, locale)` runs `agent_roles_errors <dir>`, extracted from `validate.sh`, under `LC_ALL=<locale>`, and returns its output lines. `agent` is `plugins/pd/agents/codebase-explorer.md`; a section of it runs from its `## ` heading to the next. `agents_copy`: a fresh `tmp_path` copy of `plugins/pd/agents/*.md`, made per case. A case's tag names the expectation whose behavior the pinned text serves; each text case names the literal substrings it checks. B3 to B6 are live dispatches the conductor runs at Verify; the cases below pin the agent text those dispatches exercise, so a missing instruction fails here first.

### Wave 1

#### Task 1: the explorer asks CodeGraph first; its tools pinned; the rename checklist line
- contract: shape.md ## Design, plugins/pd/agents/codebase-explorer.md, validate.sh, plugins/pd/skills/designing/SKILL.md, plugins/pd/skills/planning/SKILL.md
- files: plugins/pd/agents/codebase-explorer.md, validate.sh, plugins/pd/skills/designing/SKILL.md, plugins/pd/skills/planning/SKILL.md, plugins/pd/scripts/test_explorer_codegraph.py, .github/workflows/ci.yml, CHANGELOG.md
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_explorer_codegraph.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1] (fixture: none): given `agent`'s frontmatter, expect its `tools:` to be, as a set, exactly Glob, Grep, Read and `mcp__codegraph__codegraph_explore`.
  - C2 [B1] (fixture: none): run `./validate.sh` under `LC_ALL=C` and under `LC_ALL=en_US.UTF-8`; expect exit 0 both times and the line "the failing fixture fails all 9 checks" in each output; and expect `validate.sh` to hold neither `of 8 errors` nor `all 8 checks`.
  - C3 [B1] (fixture: agents_copy): with `agent`'s tools in the copy reordered to `[mcp__codegraph__codegraph_explore, Read, Grep, Glob]`, expect `roles(copy, C)` and `roles(copy, en_US.UTF-8)` both empty (order and locale don't matter); with that reordered list plus `Write`, expect each to be exactly one line naming `codebase-explorer` (true only once the explorer role exists).
  - C4 [B2] (fixture: agents_copy): with `agent`'s tools in the copy set to `[Glob, Grep, Read, Write]`, expect `roles(copy, C)` to be exactly one line, naming `codebase-explorer` and `Write`; with them set to `[Glob, Grep, Read]` (the old list), expect exactly one line naming `codebase-explorer` and `(has Glob,Grep,Read)`.
  - C5 [B3, B4, B5] (fixture: none): in `agent`'s `## Research Process`, expect step 1 to stay "Parse the query" (no tool), the first numbered step naming a tool to name `mcp__codegraph__codegraph_explore` and to come before every numbered step naming Glob or Grep; the section to hold `tool not in session`, `no index`, `error: `, `timeout` and `.codegraph/` (what makes the tool unavailable, and its three reasons), and a step holding `Glob, Grep and Read` with `what CodeGraph didn't answer` and `unavailable`. In `## Search Strategies`, expect "For features"'s first item to name `codegraph_explore`; among the must-nots, expect `Read files without searching first (CodeGraph, Glob or Grep)`.
  - C10 [B3, B4] (fixture: none): in `agent`'s `## Research Process`, expect `naming no symbol` (such a query still makes the one CodeGraph call first) and, for several CodeGraph calls, `answered` with `returned results` (a no-index answer or an error isn't an answer) and `first call's reason`. The live runs at Verify don't happen to hit these two branches, so their text is what this plan pins.
  - C11 [B3] (fixture: none): in `agent`'s body, expect `its own output shape` and `leave out "search"`: when the dispatch asks for its own output shape (a schema in its prompt or tools), the explorer returns that shape without `search`.
  - C6 [B3, B6] (fixture: none): parse the two JSON examples in `agent`'s `## Output Format` (today's two, each gaining `search`); expect each object's keys to be exactly `findings`, `no_findings_reason` and `search`, and each finding's keys exactly `finding`, `source` and `relevance`, the first example's `relevance` staying today's `"high | medium | low"`; expect the first example's `search` to be `"codegraph | codegraph, then grep | grep (codegraph unavailable: <reason>)"` and the second's `"grep (codegraph unavailable: no index)"` (adding `search` is the only output change).
  - C7 [B3] (fixture: none): in `agent`'s body, expect the stale-index rule: `edited since the last index sync` and `auto-sync is DISABLED` (the openings of CodeGraph's two banners) with `Read each file a finding rests on before citing it`.
  - C8 [B7] (fixture: none): in `plugins/pd/skills/designing/SKILL.md` and `plugins/pd/skills/planning/SKILL.md`, expect exactly one line in each `## Review checklist` section starting `- **Renames and store moves list their surfaces:**`, equal to a literal in the test copied from shape.md's RenameChecklistLine block.
  - C9 [B1] (fixture: none): read `.github/workflows/ci.yml`; expect its `uv run --project plugins/pd pytest` line to name `plugins/pd/scripts/test_explorer_codegraph.py` (that line lists files one by one). Also expect `CHANGELOG.md`'s `[Unreleased]` section to hold a line naming `codebase-explorer` and CodeGraph.
