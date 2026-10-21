---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/dev_artifacts/plans/2026-10-14-thin-pd-native-design.md)
---

# Installation

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Claude Code | latest |
| git | any |
| Python 3 | pd's scripts use only the standard library, except `pd-html.py` |
| uv | runs `pd-html.py` (Markdown to HTML) with its one dependency |
| jq | `pd-session-start.sh` reads its input and writes its output with jq; without it, the hook gives Claude nothing |

### Optional

- **[Codex plugin](https://github.com/openai/codex-plugin-cc):** reviews first at Contracts, Plan and Verify unless your CLAUDE.md has the line `**Codex reviewer: DISABLED**`. When it's disabled, missing or fails twice, a Claude reviewer does the review.
- **[calvin skill](https://github.com/clthuang/calvin):** questions the criteria at Criteria, run by the `calvin-runner` agent. `/pd:init` reports it when it's missing, and without it `/pd:specify` asks whether to sign off anyway.
- **`gh`:** `/pd:finish-workitem` uses it to push, open and merge a PR when the base branch's rules require a pull request.

## Install

In a Claude Code session (`#stable` follows releases):

```bash
/plugin marketplace add clthuang/pedantic-drip#stable
/plugin install pd@pedantic-drip-marketplace
```

## Update

A release reaches your install when you update the marketplace and the plugin. In a terminal:

```bash
claude plugin marketplace update pedantic-drip-marketplace
claude plugin update pd@pedantic-drip-marketplace
```

Restart Claude Code to load the new version.

**A marketplace added without `#stable`** follows `main`, not releases. Check its source with `claude plugin marketplace list`: a current entry shows `clthuang/pedantic-drip@stable`. For any other source, remove the entry, then run both [Install](#install) commands again:

```bash
claude plugin marketplace remove pedantic-drip-marketplace
```

## Set a Project Up

Run `/pd:init` once per project, before the first work item: every pd workflow needs the `workflow_output_cap` it writes, and Verify needs `qa_battery`. It writes `.claude/pd.local.md` (`artifacts_root`, `base_branch`, `qa_battery`, the test paths and the budgets) and proposes these `.claude/settings.json` entries, as a diff you approve:

- **`worktree.baseRef: "head"`:** each task's worktree starts from the work item's branch, not the default branch.
- **`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`:** agents can't spawn agents.
- **Allow rules** for `git merge`, `git worktree` and the `qa_battery` commands, so an unattended `/goal` run isn't stopped by a permission prompt.

An old-layout pd project (`docs/features/` without `sop: 1` in `.claude/pd.local.md`) runs `/pd:adopt` instead.

## Check It Works

1. **Start a session in the project** and ask Claude for `pd_artifacts_root` and `pd_base_branch`. The SessionStart hook puts these values in Claude's context; it doesn't print them. An old-layout project gets only the "run /pd:adopt" line.
2. **Run the status script** of the installed version:

   ```bash
   "$(jq -r '.plugins["pd@pedantic-drip-marketplace"][0].installPath' ~/.claude/plugins/installed_plugins.json)/scripts/pd-status"
   ```

   It prints the project's items by status, each plan's progress, open blockers and retros owed; an old-layout project gets the "run /pd:adopt" line. The path comes from `~/.claude/plugins/installed_plugins.json` because `~/.claude/plugins/cache/` can hold several pd versions at once.
