#!/bin/bash
# Asserts FR-C-115.1 atomicity across merge-base..HEAD on the feature branch.
# Runs at /pd:finish-feature Step 5a (pre-merge validation; registered in validate.sh).
# Exit 0 if invariant holds OR if FR-C-115 work is not present on this branch.
# Exit 1 if violated.

set -euo pipefail

BASE_BRANCH="${1:-develop}"

# If base branch doesn't exist locally (fresh clone, detached HEAD, etc.), skip.
if ! git rev-parse --verify "$BASE_BRANCH" >/dev/null 2>&1; then
    exit 0
fi

MERGE_BASE=$(git merge-base "$BASE_BRANCH" HEAD)

# Locate the FR-C-115.1 commit by marker on the feature branch.
SHA=$(git log --grep='^FR-C-115.1:' --pretty=format:%H "${MERGE_BASE}..HEAD" | head -1)

if [[ -z "$SHA" ]]; then
    # No FR-C-115.1 commit on branch — check if either change-half slipped through unmarked.
    UNMARKED_DB=$(git diff "$MERGE_BASE..HEAD" -- plugins/pd/hooks/lib/entity_registry/database.py \
        | grep -cE '^\+.*append_phase_event.*entity_status_changed' || true)
    UNMARKED_WSS=$(git diff "$MERGE_BASE..HEAD" -- plugins/pd/mcp/workflow_state_server.py \
        | grep -cE '^-.*append_phase_event.*entity_status_changed' || true)
    if [[ "$UNMARKED_DB" -gt 0 || "$UNMARKED_WSS" -gt 0 ]]; then
        echo "ERROR: FR-C-115 change-half present without marked commit. Atomicity unverified." >&2
        echo "  Unmarked database.py emit additions: $UNMARKED_DB" >&2
        echo "  Unmarked workflow_state_server.py emit deletions: $UNMARKED_WSS" >&2
        exit 1
    fi
    exit 0
fi

# Marker commit found; verify atomicity invariant via git show assertions.
git show "$SHA" --name-only | grep -q 'plugins/pd/hooks/lib/entity_registry/database.py' || {
    echo "ERROR: $SHA missing database.py" >&2; exit 1
}
git show "$SHA" --name-only | grep -q 'plugins/pd/mcp/workflow_state_server.py' || {
    echo "ERROR: $SHA missing workflow_state_server.py" >&2; exit 1
}
git show "$SHA" -- plugins/pd/hooks/lib/entity_registry/database.py | grep -qE '^\+.*append_phase_event.*entity_status_changed' || {
    echo "ERROR: $SHA missing emit insertion in database.py" >&2; exit 1
}
git show "$SHA" -- plugins/pd/mcp/workflow_state_server.py | grep -qE '^-.*append_phase_event.*entity_status_changed' || {
    echo "ERROR: $SHA missing manual emit deletion in workflow_state_server.py" >&2; exit 1
}
exit 0
