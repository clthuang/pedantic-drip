#!/usr/bin/env bash
set -euo pipefail

# Color helpers (respect NO_COLOR)
if [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; NC=''
fi

# Output helpers
die()  { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}Warning: $*${NC}" >&2; }
ok()   { echo -e "${GREEN}$*${NC}" >&2; }
info() { echo -e "$*" >&2; }
step() { echo -e "Step $1: $2..." >&2; }

# Path constants
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
IFLOW_DIR="${HOME}/.claude/iflow"
MEMORY_DIR="${IFLOW_DIR}/memory"
MEMORY_DB="${MEMORY_DIR}/memory.db"
ENTITY_DIR="${IFLOW_DIR}/entities"
ENTITY_DB="${ENTITY_DB_PATH:-${ENTITY_DIR}/entities.db}"
MIGRATE_DB="${SCRIPT_DIR}/migrate_db.py"

# Python path resolution
resolve_python() {
    local venv_python="${SCRIPT_DIR}/../plugins/iflow/.venv/bin/python"
    if [ -x "$venv_python" ]; then
        echo "$venv_python"; return
    fi
    # Plugin cache (Glob pattern)
    local cache_python
    cache_python="$(ls ~/.claude/plugins/cache/*/iflow*/*/.venv/bin/python 2>/dev/null | head -1)"
    if [ -n "${cache_python:-}" ] && [ -x "$cache_python" ]; then
        echo "$cache_python"; return
    fi
    # System fallback
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"; return
    fi
    return 1
}
PYTHON="$(resolve_python)" || die "Python 3 required for SQLite operations. Install Python or run: plugins/iflow/scripts/setup.sh"

# Session detection
check_active_session() {
    if pgrep -f 'memory_server|entity_server|workflow_state_server' > /dev/null 2>&1; then
        return 0
    fi
    local wal_files=("${MEMORY_DB}-wal" "${ENTITY_DB}-wal")
    for wal in "${wal_files[@]}"; do
        if [ -f "$wal" ] && [ "$(stat -f%z "$wal" 2>/dev/null || stat -c%s "$wal" 2>/dev/null)" -gt 0 ]; then
            return 0
        fi
    done
    return 1
}

# JSON extraction helper
extract_json_field() {
    local json_str="$1" field="$2"
    "$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])" "$json_str" "$field"
}

# File copy helpers
copy_file() {
    local src="$1" dst="$2"
    if [ -f "$dst" ] && [ "${FORCE:-0}" != "1" ]; then
        return 1  # skipped
    fi
    cp "$src" "$dst"
    return 0  # copied
}

copy_markdown_files() {
    local src_dir="$1" dst_dir="$2"
    local added=0 skipped=0
    for md in "$src_dir"/*.md; do
        [ -f "$md" ] || continue
        local basename
        basename="$(basename "$md")"
        if copy_file "$md" "$dst_dir/$basename"; then
            added=$((added + 1))
        else
            skipped=$((skipped + 1))
        fi
    done
    info "  added $added, skipped $skipped"
}

# Plugin version resolution
resolve_plugin_version() {
    local pjson
    pjson="$(ls ~/.claude/plugins/cache/*/iflow*/*/plugin.json 2>/dev/null | head -1)"
    if [ -z "${pjson:-}" ]; then
        # Fallback: dev workspace
        pjson="${SCRIPT_DIR}/../plugins/iflow/plugin.json"
    fi
    if [ -f "$pjson" ]; then
        "$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$pjson"
    else
        echo "unknown"
    fi
}

# Help text
show_help() {
    cat <<'HELP'
Usage: migrate.sh {export|import|help}

Commands:
  export [output-path] [--force]    Export iflow state to a bundle
  import <bundle-path> [--dry-run] [--force]  Import iflow state from a bundle
  help                               Show this help message

Options:
  --force     Proceed even if active Claude session detected
  --dry-run   Preview what would be restored (import only)

Examples:
  migrate.sh export
  migrate.sh export ~/my-backup.tar.gz
  migrate.sh import ~/iflow-export-20260316-025408.tar.gz
  migrate.sh import --dry-run ~/backup.tar.gz
HELP
}

# Subcommand dispatch
FORCE=0
DRY_RUN=""

main() {
    local cmd="${1:-help}"
    shift || true

    # Parse global flags from remaining args
    local positional=()
    for arg in "$@"; do
        case "$arg" in
            --force) FORCE=1 ;;
            --dry-run) DRY_RUN="--dry-run" ;;
            *) positional+=("$arg") ;;
        esac
    done

    case "$cmd" in
        export)  export_flow "${positional[@]+"${positional[@]}"}" ;;
        import)  import_flow "${positional[@]+"${positional[@]}"}" ;;
        help|--help|-h) show_help ;;
        *)       echo "Usage: migrate.sh {export|import|help}" >&2; exit 1 ;;
    esac
}

# Placeholder flows (Steps 10, 11 will implement these)
export_flow() { die "export_flow not yet implemented"; }
import_flow() { die "import_flow not yet implemented"; }

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
