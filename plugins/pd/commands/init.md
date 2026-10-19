---
description: Set a project up for pd once — config, artifacts root, proposed settings
argument-hint: "[--force]"
---

# /pd:init

**Purpose:** set the current git repository up for pd, once (plan Part B §12, "A new project"). Run it before the first work item: every pd workflow needs the `workflow_output_cap` it writes, and Verify needs `qa_battery`.

**Steps:**
1. **When the session-start line offered this command** (the user didn't type `/pd:init`), ask first through AskUserQuestion: "Run /pd:init now", "Not now", "Never for this repository".
   - **Not now:** stop. The next session asks again.
   - **Never (the decline path):** run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-init --decline`, then stop. It records the repository in `~/.claude/pd/init-declined`, one line per repository: its `origin` URL, or its path when it has none. The session-start hook reads that file and stops asking.
2. **Run** `${CLAUDE_PLUGIN_ROOT}/scripts/pd-init` (with `--force` only when the user passed it). It writes `.claude/pd.local.md` with every §12 field, creates `docs/dev_artifacts/backlog.md`, adds `agent_sandbox/`, `.claude/worktrees/` and `docs/_html/` to `.gitignore`, and prints a settings diff it does not apply. It refuses an existing `pd.local.md` without `--force`, and an old-layout pd project: relay its "run /pd:adopt" line and stop.
3. **Confirm the proposals:** show the proposed `source_paths`, `test_paths`, `fixture_paths`, `languages` and `qa_battery` from `.claude/pd.local.md`, and ask through AskUserQuestion: keep them, or name changes. Apply named changes with Edit.
4. **Tracker:** when pd-init printed its GitHub line, run `gh auth status`. Only if it passes, ask through AskUserQuestion: `tracker: none` or `tracker: github`. First run `gh repo view --json visibility`, and when it says `PUBLIC`, warn that issues will be public.
5. **Missing tools:** relay each `MISSING:` line (uv, the `calvin` skill) with its install hint.
6. **Settings:** show the settings diff pd-init printed, then ask through AskUserQuestion: "Apply the settings diff" or "Don't apply". On "Apply", run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-init --apply-settings`.
   - `worktree.baseRef: "head"`: task worktrees start from the work item's branch, not the default branch.
   - `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`: no agent spawns agents.
   - The allow rules: `git merge`, `git worktree` and the `qa_battery` commands, so auto mode doesn't block an unattended goal run.
7. **Explain the launch variables** (Part B §8; §A5 cap 2):
   - `CLAUDE_CODE_TASK_LIST_ID=<id>` shares a work item's task list across sessions.
   - `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` turns the task list on for models newer than those the Claude Code docs list.
   - `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` and `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` cap how many agents run at once; they keep their defaults unless the user sets them.
8. **Stage nothing.** List the changed files (`.claude/pd.local.md`, `.gitignore`, `docs/dev_artifacts/backlog.md`, and `.claude/settings.json` if applied) for the user to review and commit.
