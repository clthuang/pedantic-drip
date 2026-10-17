---
last-updated: 2026-10-18T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
audit-feature: 098-tier-doc-frontmatter-sweep
---

# Installation

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Claude Code | latest |
| git | any |
| Python 3 | pd's scripts are standard-library Python |
| uv | runs `pd-html.py` (Markdown to HTML) |

## Install

In a Claude Code session (`#stable` follows releases):

```bash
/plugin marketplace add clthuang/pedantic-drip#stable
/plugin install pd@pedantic-drip-marketplace
```

## Set a Project Up

Run `/pd:init` once per project. It writes `.claude/pd.local.md` (`artifacts_root`, `base_branch`, `qa_battery`, the test paths and the budgets) and proposes these `.claude/settings.json` entries, as a diff you approve:

- **`worktree.baseRef: "head"`:** each task's worktree starts from the feature branch, not the default branch.
- **`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`:** agents can't spawn agents.
- **Allow rules** for `git merge`, `git worktree` and the `qa_battery` commands, so an unattended `/goal` run isn't stopped by a permission prompt.

An old-layout pd project (`docs/features/` without `sop: 1` in `.claude/pd.local.md`) runs `/pd:adopt` instead.

## Check It Works

Start a session in the project: the SessionStart summary prints `pd_artifacts_root` and `pd_base_branch`. Then run the status script:

```bash
"$(ls -d ~/.claude/plugins/cache/*/pd/*/scripts | head -1)/pd-status"
```

It prints the project's items by status, each plan's progress, open blockers and retros owed.
