#!/usr/bin/env bash
# migrate-from-iflow.sh — Idempotent migration from iflow layout to pd layout.
#
# BOOTSTRAPPING: You must `git pull` to get this script. If you're reading this
# on a machine that still has the old layout, run:
#   git pull origin develop
#   bash scripts/migrate-from-iflow.sh
#
# Usage:
#   bash scripts/migrate-from-iflow.sh            # run migration
#   bash scripts/migrate-from-iflow.sh --dry-run  # preview without changes
#
# Steps:
#   1. Migrate global data dir (~/.claude/iflow → ~/.claude/pd)
#   2. Clear stale plugin cache entries
#   3. Recreate Python venv (requires `uv` and network)
#   4. Rename per-project config files
#   5. Update config variable names
#   6. Update git remote URL

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

CHANGES_NEEDED=false

log()  { printf '  %s\n' "$*"; }
info() { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m✗\033[0m %s\n' "$*"; }
dry()  { $DRY_RUN && printf '  \033[2m(dry run — skipped)\033[0m\n'; }

# ---------- Pre-flight ----------

info "Checking if migration is needed..."

GLOBAL_OLD="$HOME/.claude/iflow"
GLOBAL_NEW="$HOME/.claude/pd"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/plugins/pd"
VENV_DIR="$PLUGIN_DIR/.venv"
CONFIG_OLD="$REPO_ROOT/.claude/iflow.local.md"
CONFIG_OLD_ALT="$REPO_ROOT/.claude/iflow-dev.local.md"
CONFIG_NEW="$REPO_ROOT/.claude/pd.local.md"
CACHE_DIR="$HOME/.claude/plugins/cache"

needs_migration() {
    # Global data dir still named iflow
    [[ -d "$GLOBAL_OLD" ]] && return 0
    # Stale cache entries
    ls -d "$CACHE_DIR"/*/iflow* 2>/dev/null | head -1 >/dev/null 2>&1 && return 0
    # Venv has old name in pyvenv.cfg
    [[ -f "$VENV_DIR/pyvenv.cfg" ]] && grep -q 'iflow' "$VENV_DIR/pyvenv.cfg" 2>/dev/null && return 0
    # Old config files exist
    [[ -f "$CONFIG_OLD" || -f "$CONFIG_OLD_ALT" ]] && return 0
    # Config has old variable names
    [[ -f "$CONFIG_NEW" ]] && grep -q 'iflow_' "$CONFIG_NEW" 2>/dev/null && return 0
    # Git remote still points to my-ai-setup
    git -C "$REPO_ROOT" remote get-url origin 2>/dev/null | grep -q 'my-ai-setup' && return 0
    return 1
}

if ! needs_migration; then
    ok "No migration needed — already on pd layout."
    exit 0
fi

$DRY_RUN && warn "DRY RUN — no changes will be made."
echo

# ---------- Step 1: Global data dir ----------

info "Step 1: Global data directory"

if [[ -d "$GLOBAL_OLD" ]]; then
    CHANGES_NEEDED=true
    if [[ -d "$GLOBAL_NEW" ]]; then
        log "Both ~/.claude/iflow and ~/.claude/pd exist — merging"
        if ! $DRY_RUN; then
            rsync -a --ignore-existing "$GLOBAL_OLD/" "$GLOBAL_NEW/"
            BACKUP="$GLOBAL_OLD.bak.$(date +%s)"
            mv "$GLOBAL_OLD" "$BACKUP"
            log "Old dir backed up to $BACKUP"
        fi
        dry
    else
        log "Renaming ~/.claude/iflow → ~/.claude/pd"
        if ! $DRY_RUN; then
            mv "$GLOBAL_OLD" "$GLOBAL_NEW"
        fi
        dry
    fi
else
    ok "Already migrated (or never existed)"
fi

# ---------- Step 2: Clear stale plugin cache ----------

info "Step 2: Clear stale plugin cache"

STALE_DIRS=$(ls -d "$CACHE_DIR"/*/iflow* 2>/dev/null || true)
if [[ -n "$STALE_DIRS" ]]; then
    CHANGES_NEEDED=true
    while IFS= read -r d; do
        log "Removing: $d"
        if ! $DRY_RUN; then
            rm -rf "$d"
        fi
        dry
    done <<< "$STALE_DIRS"
else
    ok "No stale cache entries"
fi

# ---------- Step 3: Recreate venv ----------

info "Step 3: Recreate Python venv"

NEED_VENV=false
if [[ -f "$VENV_DIR/pyvenv.cfg" ]] && grep -q 'iflow' "$VENV_DIR/pyvenv.cfg" 2>/dev/null; then
    NEED_VENV=true
elif [[ ! -d "$VENV_DIR" ]]; then
    NEED_VENV=true
fi

if $NEED_VENV; then
    CHANGES_NEEDED=true
    if ! command -v uv &>/dev/null; then
        err "uv is required but not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    log "Recreating venv (requires network for uv sync)"
    if ! $DRY_RUN; then
        rm -rf "$VENV_DIR"
        (cd "$PLUGIN_DIR" && uv venv && uv sync)
    fi
    dry
else
    ok "Venv is current"
fi

# ---------- Step 4: Rename per-project config ----------

info "Step 4: Per-project config files"

if [[ -f "$CONFIG_OLD" ]]; then
    CHANGES_NEEDED=true
    if [[ -f "$CONFIG_NEW" ]]; then
        log "Both $CONFIG_OLD and $CONFIG_NEW exist — keeping $CONFIG_NEW, removing old"
        if ! $DRY_RUN; then
            rm "$CONFIG_OLD"
        fi
        dry
    else
        log "Renaming iflow.local.md → pd.local.md"
        if ! $DRY_RUN; then
            mv "$CONFIG_OLD" "$CONFIG_NEW"
        fi
        dry
    fi
elif [[ -f "$CONFIG_OLD_ALT" ]]; then
    CHANGES_NEEDED=true
    if [[ -f "$CONFIG_NEW" ]]; then
        log "Both $CONFIG_OLD_ALT and $CONFIG_NEW exist — keeping $CONFIG_NEW, removing old"
        if ! $DRY_RUN; then
            rm "$CONFIG_OLD_ALT"
        fi
        dry
    else
        log "Renaming iflow-dev.local.md → pd.local.md"
        if ! $DRY_RUN; then
            mv "$CONFIG_OLD_ALT" "$CONFIG_NEW"
        fi
        dry
    fi
else
    ok "Config files already renamed"
fi

# Warn about other projects
OTHER_PROJECTS=$(find "$HOME/projects" -maxdepth 3 -name "iflow*.local.md" -path "*/.claude/*" 2>/dev/null || true)
if [[ -n "$OTHER_PROJECTS" ]]; then
    warn "Found old config files in OTHER projects (fix manually):"
    while IFS= read -r f; do
        log "  $f"
    done <<< "$OTHER_PROJECTS"
fi

# ---------- Step 5: Update config variable names ----------

info "Step 5: Config variable names"

if [[ -f "$CONFIG_NEW" ]] && grep -q 'iflow_' "$CONFIG_NEW" 2>/dev/null; then
    CHANGES_NEEDED=true
    log "Replacing iflow_ → pd_ in pd.local.md"
    if ! $DRY_RUN; then
        sed -i '' 's/iflow_/pd_/g' "$CONFIG_NEW"
    fi
    dry
else
    ok "Config variables already updated"
fi

# ---------- Step 6: Update git remote URL ----------

info "Step 6: Git remote URL"

ORIGIN_URL=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)
if echo "$ORIGIN_URL" | grep -q 'my-ai-setup'; then
    CHANGES_NEEDED=true
    NEW_URL="${ORIGIN_URL//my-ai-setup/pedantic-drip}"
    log "Updating origin: $ORIGIN_URL → $NEW_URL"
    if ! $DRY_RUN; then
        git -C "$REPO_ROOT" remote set-url origin "$NEW_URL"
    fi
    dry
else
    ok "Remote URL already updated"
fi

# ---------- Post-flight ----------

echo
if $CHANGES_NEEDED; then
    if $DRY_RUN; then
        warn "Dry run complete — re-run without --dry-run to apply changes."
    else
        ok "Migration complete!"
        # Run doctor if available
        DOCTOR="$PLUGIN_DIR/scripts/doctor.sh"
        if [[ -f "$DOCTOR" ]]; then
            echo
            info "Running health check..."
            bash "$DOCTOR" || true
        fi
    fi
else
    ok "No migration needed — already on pd layout."
fi
