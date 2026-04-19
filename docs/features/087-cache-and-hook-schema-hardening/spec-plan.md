# Feature 087: Cache & Hook-Schema Hardening (PRD + Spec + Design + Plan)

Source: RCA `docs/rca/20260419-hookSpecificOutput-missing-hookEventName-round2.md`. Four preventative items stop the regression class that caused user-facing `PreToolUse:Bash hook error` (hookSpecificOutput missing hookEventName) from recurring.

## Problem Statement

Feature 080-era bug (commit `bbfc63a`) emitted `hookSpecificOutput` from `post-enter-plan.sh` / `post-exit-plan.sh` without the required `hookEventName` key. The bug was dormant until CC tightened schema validation; fix shipped in v4.15.7 (commit `6d37153`). But the same class can recur: (1) any future hook author forgets `hookEventName`; (2) stale cached versions persist on disk and break users on long-running sessions; (3) CC's error attribution ("PreToolUse:Bash hook error" for a PostToolUse hook bug) makes diagnosis hard.

## Scope

### In scope
1. **FR-1 Static scanner** in `validate.sh` catching `hookSpecificOutput` emissions missing `hookEventName` — fails CI on regression.
2. **FR-2 Shared `emit_hook_json` helper** in `plugins/pd/hooks/lib/common.sh` that guarantees schema compliance — individual hook authors can't forget required fields.
3. **FR-3 Stale-cache cleanup** — extend existing `sync-cache.sh` (or add a new SessionStart-adjacent hook) to delete cached `pd/X.Y.Z/` directories older than the version in `installed_plugins.json`.
4. **FR-4 Documentation** in `docs/dev_guides/hook-development.md` covering (a) the `hookEventName` contract, (b) CC's cross-event error attribution, (c) preferred `emit_hook_json` helper usage.

### Out of scope
- Migrating existing hooks to use `emit_hook_json` (they already emit correct JSON post-v4.15.7; migration is pure-refactor and can be a follow-up).
- Cleaning up other projects' caches (user-side action).
- Retroactive fix on older pd versions (infeasible — they're immutable artifacts).

## Success Criteria

- [ ] SC-1: New `validate.sh` section greps `plugins/pd/hooks/` for `hookSpecificOutput` emissions; every match must include `hookEventName` within the same JSON literal. Deliberate injection of a bad emission causes validate.sh to exit non-zero with a specific message.
- [ ] SC-2: `plugins/pd/hooks/lib/common.sh` (new) exports `emit_hook_json(event_name, payload_json)` that wraps payload with `{"hookSpecificOutput": {"hookEventName": "<event>", ...payload}}`. Pytest/bats-style test proves the invariant.
- [ ] SC-3: Stale-version cleanup logic in `sync-cache.sh` (or equivalent) — given `installed_plugins.json` listing pd v4.15.9, any `cache/pedantic-drip-marketplace/pd/X.Y.Z/` where `X.Y.Z != 4.15.9` is deleted. Dry-run option for safety. Unit test (bash) with tmp-dir fixture.
- [ ] SC-4: `docs/dev_guides/hook-development.md` has a new section covering the 3 documentation items (hookEventName contract, cross-event attribution, helper usage).
- [ ] SC-5: `./validate.sh` exits 0; no regression.
- [ ] SC-6: CHANGELOG updated.

## Design

### Component 1: Static scanner (FR-1)

Append to `validate.sh` after the existing docs-sync section (around line 850):

```bash
# --- hook-schema: hookSpecificOutput must include hookEventName (feature 080/085/086 RCA) ---
# Find every file that emits `hookSpecificOutput`, then for each, verify that
# the SAME file contains `hookEventName`. This is a weak heuristic but catches
# the single-file regression class that the RCA identified.
bad_hook_emissions=0
for f in $(grep -rlE '"hookSpecificOutput"' plugins/pd/hooks/ 2>/dev/null || true); do
    if ! grep -qE '"hookEventName"' "$f"; then
        echo "FAIL: hookSpecificOutput in $f missing hookEventName"
        bad_hook_emissions=$((bad_hook_emissions + 1))
    fi
done
[ "$bad_hook_emissions" = "0" ] || exit 1
```

Weakness: accepts `hookEventName` anywhere in the file (not guaranteed to be in the same JSON object). Tradeoff: simple grep vs. full JSON parse. Good enough for bash hook files where each typically emits a single block.

### Component 2: Shared helper (FR-2)

New file `plugins/pd/hooks/lib/common.sh`:

```bash
#!/usr/bin/env bash
# Shared helpers for pd hook scripts.
#
# Feature 087: emit_hook_json — guarantees hookSpecificOutput includes
# hookEventName, preventing the class of CC schema-validation errors
# documented in docs/rca/20260419-hookSpecificOutput-missing-hookEventName-round2.md

# Emit a Claude Code hook JSON response to stdout.
#
# Args:
#   $1 — event name (e.g. "PreToolUse", "PostToolUse", "SessionStart")
#   $2 — JSON body for hookSpecificOutput (e.g. '{"permissionDecision":"allow"}')
#
# Outputs a single-line JSON with hookEventName wrapped in.
emit_hook_json() {
    local event="$1"
    local payload="${2:-{}}"
    # Merge hookEventName with payload using jq if available, else string splice.
    if command -v jq >/dev/null 2>&1; then
        jq -cn --arg evt "$event" --argjson payload "$payload" \
            '{hookSpecificOutput: ($payload + {hookEventName: $evt})}'
    else
        # Fallback: splice at the opening brace of payload.
        # Assumes payload is a valid JSON object starting with "{"
        local inner="${payload#\{}"
        if [ "$inner" = "$payload" ] || [ -z "$inner" ] || [ "$inner" = "}" ]; then
            printf '{"hookSpecificOutput":{"hookEventName":"%s"}}\n' "$event"
        else
            printf '{"hookSpecificOutput":{"hookEventName":"%s",%s}\n' "$event" "$inner"
        fi
    fi
}
```

Hooks can opt-in via `source "$(dirname "$0")/lib/common.sh"; emit_hook_json "PreToolUse" '{"permissionDecision":"allow"}'`.

### Component 3: Stale-cache cleanup (FR-3)

Extend `plugins/pd/hooks/sync-cache.sh` (exists; used for sync/re-install) with a `--cleanup-stale-versions` flag, OR add a new hook `plugins/pd/hooks/cleanup-stale-versions.sh` invoked from SessionStart.

**Chose**: new standalone hook (cleaner single-responsibility; sync-cache.sh has a different concern). Hook script:

```bash
#!/usr/bin/env bash
# Delete cached pd plugin versions older than the currently-active one.
# Invoked from SessionStart — idempotent + fast (skip if no stale dirs).
#
# Reads ~/.claude/plugins/installed_plugins.json to find the active pd
# version. Lists cache/pedantic-drip-marketplace/pd/X.Y.Z/ directories.
# Deletes any that don't match the active version.

set -euo pipefail

INSTALLED_JSON="$HOME/.claude/plugins/installed_plugins.json"
CACHE_DIR="$HOME/.claude/plugins/cache/pedantic-drip-marketplace/pd"

[ -f "$INSTALLED_JSON" ] || exit 0
[ -d "$CACHE_DIR" ] || exit 0

# Parse active pd version from installed_plugins.json using python (stdlib).
active_version=$(python3 -c "
import json, sys
try:
    data = json.load(open('$INSTALLED_JSON'))
    pd = data.get('plugins', {}).get('pd@pedantic-drip-marketplace', [])
    print(pd[0]['version'] if pd else '')
except Exception:
    print('')
" 2>/dev/null)

[ -n "$active_version" ] || exit 0

# Enumerate version dirs; delete anything !~ active.
deleted=0
for dir in "$CACHE_DIR"/*/; do
    [ -d "$dir" ] || continue
    version=$(basename "$dir")
    if [ "$version" != "$active_version" ]; then
        rm -rf "$dir"
        deleted=$((deleted + 1))
    fi
done

# Silent unless stale was removed — avoid SessionStart noise.
[ "$deleted" -eq 0 ] || \
    echo "[pd] cleaned $deleted stale cached version(s); active: $active_version" >&2
```

Register in `plugins/pd/hooks/hooks.json` as a SessionStart hook (low priority — after session-start.sh).

### Component 4: Documentation (FR-4)

Append section to `docs/dev_guides/hook-development.md`:

```markdown
## Hook JSON Output Schema

Claude Code enforces a schema on hook JSON output. When your hook emits a `hookSpecificOutput` block, the block MUST include `hookEventName` matching the event the hook is registered for:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow"
  }
}
```

### Common pitfall: missing `hookEventName`

Forgetting `hookEventName` produces this error:
```
PreToolUse:Bash hook error — Hook JSON output validation failed: hookSpecificOutput is missing required field "hookEventName"
```

### Cross-event error attribution

**The error label is MISLEADING.** CC attributes a hook's JSON validation failure to the NEXT tool event in the transcript, not to the hook that actually produced the malformed JSON. If you see `PreToolUse:Bash hook error` but your pd PreToolUse:Bash hooks look fine, grep all hooks for `hookSpecificOutput` — the bug is likely in a PostToolUse or PostToolUse:EnterPlanMode hook that fired just before.

### Preferred: use the shared helper

Instead of emitting JSON by hand, source `lib/common.sh` and call `emit_hook_json`:

```bash
source "$(dirname "$0")/lib/common.sh"
emit_hook_json "PreToolUse" '{"permissionDecision":"allow"}'
```

This guarantees `hookEventName` is always present.

### Enforcement

`validate.sh` runs a static scanner on every PR: any `hookSpecificOutput` emission without `hookEventName` in the same file fails CI.
```

## Plan

1. Write `plugins/pd/hooks/lib/common.sh` with `emit_hook_json`.
2. Add unit test for `emit_hook_json` (bats or bash self-test).
3. Add `plugins/pd/hooks/cleanup-stale-versions.sh`.
4. Register in `plugins/pd/hooks/hooks.json` as SessionStart (low priority).
5. Add scanner block to `validate.sh`.
6. Test scanner: inject a bad emission in a throwaway hook, confirm validate.sh fails.
7. Write documentation section in `docs/dev_guides/hook-development.md`.
8. Run `./validate.sh` → exit 0.
9. CHANGELOG.
10. Commit, merge, release.

## Tasks

### Task 1: common.sh helper + self-test
Write `plugins/pd/hooks/lib/common.sh` with `emit_hook_json`. Add a small self-test at the bottom that runs when the file is executed directly (not sourced): emit known payloads, parse via `python3 -c`, assert `hookEventName` present.

### Task 2: cleanup-stale-versions.sh
Write the script. Add to `hooks.json` registration. Smoke-test by creating tmp pd cache with fake versions, running the script, verifying only active remains.

### Task 3: validate.sh scanner
Add the grep-based scanner block after existing hook-schema validation section. Test locally via deliberate injection.

### Task 4: Docs section
Append to `docs/dev_guides/hook-development.md`.

### Task 5: CHANGELOG + version bump + commit + merge + release.
