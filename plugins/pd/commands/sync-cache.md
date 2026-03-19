---
description: Sync plugin source files to cache
---

# /pd:sync-cache Command

Sync the pd plugin source files to the Claude Code cache directory.

## What Gets Synced

1. **Plugin files**: Source plugin files are synced to the installed plugin cache path (auto-detected from `installed_plugins.json`)
2. **Marketplace metadata**: Source `marketplace.json` is synced to the marketplace cache, ensuring plugin name/version display correctly

## Instructions

1. Run the sync script from the project source:
   ```bash
   ./plugins/pd/hooks/sync-cache.sh
   ```

2. Report the result:
   - If successful: "Plugin cache synced successfully."
   - If failed: Report the error message.
