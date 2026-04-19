#!/usr/bin/env bash
# cleanup-stale-versions.sh — delete cached pd plugin versions older
# than the currently-active one.
#
# Feature 087: prevents long-running CC sessions from picking up buggy
# pre-fix hook scripts from stale cached installs. Idempotent + fast:
# returns quickly when no stale dirs exist, silent unless it actually
# removes something.
#
# Registered as a SessionStart hook (low priority — runs after session-
# start.sh). Reads ~/.claude/plugins/installed_plugins.json to find the
# active pd version, then deletes any cache/pedantic-drip-marketplace/
# pd/X.Y.Z/ directory that doesn't match.
#
# The script takes no stdin and emits no stdout on the success path so
# it doesn't corrupt SessionStart context injection. Errors go to stderr.

set -uo pipefail

INSTALLED_JSON="$HOME/.claude/plugins/installed_plugins.json"
CACHE_DIR="$HOME/.claude/plugins/cache/pedantic-drip-marketplace/pd"

# Preconditions: both paths must exist.
[[ -f "$INSTALLED_JSON" ]] || exit 0
[[ -d "$CACHE_DIR" ]] || exit 0

# Extract active pd version from installed_plugins.json via python stdlib.
# Python is preferred over jq because pd targets stdlib only (NFR-3).
active_version=$(python3 - <<'PYEOF' 2>/dev/null || echo ""
import json
import os
try:
    path = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
    data = json.load(open(path))
    plugins = data.get("plugins", {})
    pd_entries = plugins.get("pd@pedantic-drip-marketplace", [])
    if pd_entries:
        print(pd_entries[0].get("version", ""))
except Exception:
    pass
PYEOF
)

# If we couldn't determine the active version, bail out silently —
# better to skip cleanup than to accidentally delete the active one.
[[ -n "$active_version" ]] || exit 0

# Enumerate version dirs; delete anything not matching active.
deleted=0
for dir in "$CACHE_DIR"/*/; do
    [[ -d "$dir" ]] || continue
    version=$(basename "$dir")
    if [[ "$version" != "$active_version" ]]; then
        # Safety: only delete dirs that look like semver (X.Y.Z),
        # so we never wipe non-version directories that may have
        # been placed here by other tooling.
        if [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            rm -rf "$dir"
            deleted=$((deleted + 1))
        fi
    fi
done

# Silent on no-op; single stderr line on successful cleanup.
if [[ "$deleted" -gt 0 ]]; then
    echo "[pd] cleanup-stale-versions: removed $deleted stale cached version(s); active: $active_version" >&2
fi

exit 0
