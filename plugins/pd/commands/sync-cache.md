---
description: Sync plugin source files to cache
---

# /pd:sync-cache Command

Sync the pd plugin source files to the Claude Code cache directory.

## What Gets Synced

1. **Plugin files**: Source plugin files are synced to the installed plugin cache path (auto-detected from `installed_plugins.json`)
2. **Marketplace metadata**: Source `marketplace.json` is synced to the marketplace cache, ensuring plugin name/version display correctly. Only a checkout that holds the pd plugin syncs it, so another plugin repository's `marketplace.json` never replaces pd's.

Only a main checkout publishes, or a directory with no `.git` (a `git archive` export). From a linked git worktree the script publishes nothing, nor from a checkout whose `.git` is a file git cannot answer for (an orphaned worktree, a failing git, or a git older than 2.31), so no worktree overwrites the shared cache with its branch's plugin; a worktree's plugin edits reach the cache once they reach the main checkout.

## Instructions

1. Run the sync script from the project source:
   ```bash
   ./plugins/pd/hooks/sync-cache.sh
   ```

2. Report the result:
   - In a linked worktree (`git rev-parse --path-format=absolute --git-dir --git-common-dir` prints two different paths), or where `.git` is a file and that command fails or prints other than two paths: "Nothing published: only the main checkout publishes the plugin cache."
   - Otherwise, if successful: "Plugin cache synced successfully."
   - If failed: Report the error message.
