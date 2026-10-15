---
description: Migrate an old-layout pd project — dry run, your review, then a pd-adopt branch
argument-hint: "[--workspace=<uuid>]"
---

# /pd:adopt

**Purpose:** the one-time migration of an old-layout pd project (a `features/` directory under the old artifacts root, `.meta.json` files and the entity registry) to the files-only layout (plan Part B §12, "An existing pd project").

**Scope:** only the repository the user named. Never run `pd-adopt` against a project the user didn't name, and never on your own initiative.

**Steps:**
1. **Confirm the target:** show the repository's path (`git rev-parse --show-toplevel`) and its current branch. Ask through AskUserQuestion: "Adopt this repository" or "Stop". Stop on anything but the first.
2. **Dry run first:** run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-adopt`, without `--apply`. Pass `--workspace <uuid>` only when the user gave one. The dry run works in a throwaway clone and changes nothing here. It prints its notes (`MAP BY HAND`, `CHECK`, `UNCLASSIFIED`), one commit subject per step and the full diff. A refusal ends the command; relay it. The refusals: a dirty tree, `sop: 1` already set, a non-empty registry `-wal` file, or a tracked symlink out of the repository.
3. **Show the dry run:** the notes first, then `git diff --stat`'s summary from the output, then where to read the full diff. List the branches open now, for their owners: `git branch --no-merged <base branch>`.
4. **Ask for the user's review** through AskUserQuestion: "Apply on a pd-adopt branch" or "Stop". Apply only on that answer.
5. **Apply on the `pd-adopt` branch:** run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-adopt --apply`. It creates `pd-adopt` from HEAD and commits plan §12's steps 0–8 there, with `sop: 1` last. Then run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-lint` on the branch, and show its result.
6. **Hand the branch over.** The user reviews it with `git log -p <base branch>..pd-adopt` and merges it to the base branch themselves. Never merge, push or delete the branch.
