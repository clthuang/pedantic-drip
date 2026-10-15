---
description: Create a feature and its branch, or promote a brainstorm, rca or backlog item
argument-hint: "\"<title>\" [--from <brainstorms/<id>.md | rca/<id>.md | backlog#<id>>] [--mode standard|small|express] | --plan <plan> <slug> \"<title>\""
---

# /pd:create-feature

Mints one feature item — its directory, `README.md` and `log.md` — through `pd-new`, and its branch. Every new feature comes through here, promoted work included. Entry, exit and commits follow the `pd:workflow-transitions` skill.

1. **Create it:** `${CLAUDE_PLUGIN_ROOT}/scripts/pd-new feature $ARGUMENTS`. It prints the new item's path, ticks a `backlog#` origin's line, and fills a roadmap's `planned:` line for `--plan`. A refusal is reported verbatim and stops the command.
2. **Promoted work gets its depth now:** for `--from`, apply `/pd:secretary`'s depth rules, set `mode:` and `risk:`, and record each skipped stage as a `phase triage -> <first stage>` entry with its reason.
3. **Branch:** `git checkout -b feature/<id>` from `{pd_base_branch}`.
4. **Express (`--mode express`): write the mini-spec now,** per the `pd:specifying` skill's "Express: the mini-spec": `pd-new` starts an express feature at `phase: implement`, so the commit hook's lint runs its express exit check on the first commit.
5. **Commit** the item, with the mini-spec, the ticked backlog line or the roadmap edit.
6. **Continue** with `/pd:specify --feature=<id>`, or `/pd:implement --feature=<id>` for express.
