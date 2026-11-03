---
from_shape: 40d4bbee579312402993e033869a4e70a23893a7
---
# Plan: codebase-explorer uses CodeGraph

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

Shared terms: `roles(dir, locale)` runs `agent_roles_errors <dir>`, extracted from `validate.sh`, under `LC_ALL=<locale>`, and returns its output lines. `agent` is `plugins/pd/agents/codebase-explorer.md`. B3 to B6 are live dispatches the conductor runs at Verify; the cases below pin the agent text those dispatches exercise, so a missing instruction fails here first.

### Wave 1

#### Task 1: the explorer asks CodeGraph first; its tools pinned; the rename checklist line
- contract: shape.md ## Design, plugins/pd/agents/codebase-explorer.md, validate.sh, plugins/pd/skills/designing/SKILL.md, plugins/pd/skills/planning/SKILL.md
- files: plugins/pd/agents/codebase-explorer.md, validate.sh, plugins/pd/skills/designing/SKILL.md, plugins/pd/skills/planning/SKILL.md, plugins/pd/scripts/test_explorer_codegraph.py, .github/workflows/ci.yml, CHANGELOG.md
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_explorer_codegraph.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1] (fixture: none): given `roles(plugins/pd/agents, C)` and `roles(plugins/pd/agents, en_US.UTF-8)`, expect both empty; given `agent`'s frontmatter, expect its `tools:` to be exactly Glob, Grep, Read and `mcp__codegraph__codegraph_explore`.
  - C2 [B1] (fixture: none): run `./validate.sh` under `LC_ALL=C` and under `LC_ALL=en_US.UTF-8`; expect exit 0 both times and the line "the failing fixture fails all 9 checks" in each output.
  - C3 [B1] (fixture: agents_copy): with `agent`'s tools in the copy reordered to `[mcp__codegraph__codegraph_explore, Read, Grep, Glob]`, expect `roles(copy, C)` and `roles(copy, en_US.UTF-8)` both empty (order and locale don't matter).
  - C4 [B2] (fixture: agents_copy): with `agent`'s tools in the copy set to `[Glob, Grep, Read, Write]`, expect `roles(copy, C)` to be exactly one line, naming `codebase-explorer` and `Write`; with them set to `[Glob, Grep, Read]` (the old list), expect one line too.
  - C5 [B3, B4, B5] (fixture: none): in `agent`'s body, expect the Research Process's first step to call `mcp__codegraph__codegraph_explore` before any Glob or Grep step, the three reason strings `tool not in session`, `no index` and `error: ` each present, and the fallback to Glob, Grep and Read named for an unavailable tool.
  - C10 [B3, B4] (fixture: none): in `agent`'s Research Process, expect the rule that a query naming no symbol still makes the one CodeGraph call first, and the rule for several CodeGraph calls: one that answered decides `search`; with none answered, the first call's reason is given (the live B3 to B6 runs don't exercise these two, so the text is what this plan can pin).
  - C11 [B3] (fixture: none): in `agent`'s body, expect the supplied-schema rule: when the dispatch supplies its own output schema, the explorer returns that shape and leaves out `search`.
  - C6 [B3, B6] (fixture: none): parse both JSON examples in `agent`'s Output Format; expect each object's keys to be exactly `findings`, `no_findings_reason` and `search`, each finding's keys exactly `finding`, `source` and `relevance`, `relevance` one of `high`, `medium`, `low`, and the three `search` values each named in the format's text (adding `search` is the only output change).
  - C7 [B3] (fixture: none): in `agent`'s body, expect the stale-index rule (read each file a finding rests on before citing it, when the banner names stale files or says auto-sync is disabled).
  - C8 [B7] (fixture: none): in `plugins/pd/skills/designing/SKILL.md` and `plugins/pd/skills/planning/SKILL.md`, expect exactly one line in each `## Review checklist` section starting `- **Renames and store moves list their surfaces:**`, equal to the RenameChecklistLine contract's text.
  - C9 [B1] (fixture: none): read `.github/workflows/ci.yml`; expect its `uv run --project plugins/pd pytest` line to name `plugins/pd/scripts/test_explorer_codegraph.py` (that line lists files one by one).
