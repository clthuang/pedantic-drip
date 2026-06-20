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
PD_DIR="${HOME}/.claude/pd"
ENTITY_DIR="${PD_DIR}/entities"
ENTITY_DB="${ENTITY_DB_PATH:-${ENTITY_DIR}/entities.db}"
MIGRATE_DB="${SCRIPT_DIR}/migrate_db.py"

# Python path resolution
resolve_python() {
    local venv_python="${SCRIPT_DIR}/../plugins/pd/.venv/bin/python"
    if [ -x "$venv_python" ]; then
        echo "$venv_python"; return
    fi
    # Plugin cache (Glob pattern)
    local cache_python
    cache_python="$(ls ~/.claude/plugins/cache/*/pd*/*/.venv/bin/python 2>/dev/null | head -1)"
    if [ -n "${cache_python:-}" ] && [ -x "$cache_python" ]; then
        echo "$cache_python"; return
    fi
    # System fallback
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"; return
    fi
    return 1
}
if [ -n "${PYTHON:-}" ]; then
    # Allow env override for testing
    if ! "$PYTHON" --version >/dev/null 2>&1; then
        die "Python 3 required for SQLite operations. Install Python or run: plugins/pd/scripts/setup.sh"
    fi
else
    PYTHON="$(resolve_python)" || die "Python 3 required for SQLite operations. Install Python or run: plugins/pd/scripts/setup.sh"
fi

# Session detection
check_active_session() {
    if pgrep -f 'entity_server|workflow_state_server' > /dev/null 2>&1; then
        return 0
    fi
    local wal_files=("${ENTITY_DB}-wal")
    for wal in "${wal_files[@]}"; do
        if [ -f "$wal" ] && [ "$(stat -f%z "$wal" 2>/dev/null || stat -c%s "$wal" 2>/dev/null)" -gt 0 ]; then
            return 0
        fi
    done
    return 1
}

# JSON extraction helpers
extract_json_field() {
    local json_str="$1" field="$2"
    "$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])" "$json_str" "$field"
}

extract_manifest_count() {
    local manifest_path="$1" file_key="$2" count_key="$3"
    "$PYTHON" -c "import json,sys; m=json.load(open(sys.argv[1])); print(m.get('files',{}).get(sys.argv[2],{}).get(sys.argv[3],0))" "$manifest_path" "$file_key" "$count_key"
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

# Plugin version resolution
resolve_plugin_version() {
    local pjson
    pjson="$(ls ~/.claude/plugins/cache/*/pd*/*/plugin.json 2>/dev/null | head -1)"
    if [ -z "${pjson:-}" ]; then
        # Fallback: dev workspace
        pjson="${SCRIPT_DIR}/../plugins/pd/plugin.json"
    fi
    if [ -f "$pjson" ]; then
        "$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$pjson"
    else
        echo "unknown"
    fi
}

# Doctor check per AC-15 and design TD-6
run_doctor_check() {
    local doctor="${SCRIPT_DIR}/../plugins/pd/scripts/doctor.sh"
    if [ ! -x "$doctor" ]; then
        doctor="$(ls ~/.claude/plugins/cache/*/pd*/*/scripts/doctor.sh 2>/dev/null | head -1)"
    fi
    if [ -n "${doctor:-}" ] && [ -x "$doctor" ]; then
        "$doctor" --quiet 2>/dev/null || warn "doctor.sh reported issues (non-fatal)"
    else
        # Inline fallback: verify DBs are readable
        local check_ok=true
        if [ -f "$ENTITY_DB" ]; then
            "$PYTHON" -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('SELECT count(*) FROM entities'); c.close()" "$ENTITY_DB" 2>/dev/null || check_ok=false
        fi
        if [ "$check_ok" = false ]; then
            warn "Inline health check detected issues (non-fatal)"
        fi
    fi
}

# Verify DB integrity after import; sets verify_errors on failure
# Usage: verify_imported_db <db_path> <table> <label> <action> <added_count>
verify_imported_db() {
    local db_path="$1" table="$2" label="$3" action="$4" added_count="$5"
    [ -f "$db_path" ] || return 0

    local expected_count
    if [ "$action" = "copied" ]; then
        expected_count=$added_count
    else
        expected_count=0  # count-only mode for merges
    fi

    local verify_output
    verify_output="$("$PYTHON" "$MIGRATE_DB" verify "$db_path" --expected-count "$expected_count" --table "$table" 2>/dev/null)" || true
    [ -n "$verify_output" ] || return 0

    local is_ok actual_count
    is_ok="$(extract_json_field "$verify_output" ok)" || true
    actual_count="$(extract_json_field "$verify_output" actual_count)" || true
    if [ "$is_ok" = "True" ]; then
        ok "  ${label}: integrity OK ($actual_count entries)"
    else
        warn "  ${label}: verification issue (expected=$expected_count, actual=$actual_count)"
        verify_errors=$((verify_errors + 1))
    fi
}

# Help text
show_help() {
    cat <<'HELP'
Usage: migrate.sh {export|import|help}

Commands:
  export [output-path] [--force]    Export pd state to a bundle
  import <bundle-path> [--dry-run] [--force]  Import pd state from a bundle
  help                               Show this help message

Options:
  --force     Proceed even if active Claude session detected
  --dry-run   Preview what would be restored (import only)

Examples:
  migrate.sh export
  migrate.sh export ~/my-backup.tar.gz
  migrate.sh import ~/pd-export-20260316-025408.tar.gz
  migrate.sh import --dry-run ~/backup.tar.gz
HELP
}

# Subcommand dispatch
FORCE=0
DRY_RUN=""

main() {
    local cmd="${1:-}"
    if [ -z "$cmd" ]; then
        echo "Usage: migrate.sh {export|import|help}" >&2
        exit 1
    fi
    shift

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

# Export and import flows
export_flow() {
    # Pre-flight: the entity database must exist
    if [ ! -f "$ENTITY_DB" ]; then
        die "No pd data found. Expected database at:\n  $ENTITY_DB"
    fi

    # Step 1: Session check
    step "1/5" "Checking for active sessions"
    if check_active_session; then
        if [ "${FORCE:-0}" != "1" ]; then
            echo -e "${RED}Error: Active Claude session detected. Close it first or use --force.${NC}" >&2
            exit 2
        fi
        warn "Active session detected — proceeding with --force"
    fi
    ok "  No conflicts"

    # Step 2: Create staging directory
    step "2/5" "Creating staging directory"
    local timestamp
    timestamp="$(date +%Y%m%d-%H%M%S)"
    local staging_name="pd-export-${timestamp}"
    local staging
    staging="$(mktemp -d)/${staging_name}"
    mkdir -p "$staging"
    # Clean up staging dir on exit (covers failures in tar/manifest steps)
    trap 'rm -rf "$(dirname "$staging")"' EXIT
    ok "  $staging"

    local entity_count=0

    # Step 3: Backup entity DB
    step "3/5" "Backing up entity database"
    if [ -f "$ENTITY_DB" ]; then
        mkdir -p "$staging/entities"
        local ent_json
        ent_json=$("$PYTHON" "$MIGRATE_DB" backup "$ENTITY_DB" "$staging/entities/entities.db" --table entities)
        entity_count=$(extract_json_field "$ent_json" entry_count)
        ok "  $entity_count entities backed up"
    else
        info "  Skipped (entities.db not found)"
    fi

    # Step 4: Copy projects.txt
    step "4/5" "Copying projects.txt"
    if [ -f "$PD_DIR/projects.txt" ]; then
        cp "$PD_DIR/projects.txt" "$staging/projects.txt"
        ok "  projects.txt copied"
    else
        info "  No projects.txt found, skipping"
    fi

    # Step 5: Generate manifest, create tar, cleanup
    step "5/5" "Generating manifest and creating archive"
    local plugin_version
    plugin_version="$(resolve_plugin_version)"
    "$PYTHON" "$MIGRATE_DB" manifest "$staging" --plugin-version "$plugin_version" > /dev/null

    # Determine output path
    local output_path="${1:-${HOME}/pd-export-${timestamp}.tar.gz}"
    tar -czf "$output_path" -C "$(dirname "$staging")" "$(basename "$staging")"
    rm -rf "$staging"

    local file_size
    file_size=$(du -h "$output_path" | cut -f1 | tr -d ' ')

    ok "  Archive created: $output_path ($file_size)"
    echo "" >&2
    ok "Export complete!"
    info "  File: $output_path"
    info "  Size: $file_size"
    info "  Entities: $entity_count"
}
import_flow() {
    local bundle_path="${1:-}"
    [ -z "$bundle_path" ] && die "Usage: migrate.sh import <bundle-path> [--dry-run] [--force]"
    [ -f "$bundle_path" ] || die "Bundle not found: $bundle_path"

    # ── Step 1: Validate bundle ──────────────────────────────
    step "1/6" "Validating bundle"
    local extract_dir
    extract_dir="$(mktemp -d)"
    trap "rm -rf '$extract_dir'" EXIT

    # Pre-extraction path traversal check (inspect tar listing before writing to disk)
    local traversal_found=0
    while IFS= read -r entry; do
        case "$entry" in
            *../*|..*)
                traversal_found=1
                break
                ;;
        esac
    done < <(tar -tzf "$bundle_path" 2>/dev/null || true)
    if [ "$traversal_found" -eq 1 ]; then
        die "Path traversal detected in bundle"
    fi

    tar -xzf "$bundle_path" -C "$extract_dir" 2>/dev/null \
        || die "Failed to extract bundle (corrupt or not a tar.gz?)"

    # Post-extraction path traversal check (belt and suspenders)
    local real_extract
    real_extract="$(cd "$extract_dir" && pwd -P)"
    while IFS= read -r f; do
        local real_f
        real_f="$(cd "$(dirname "$f")" && pwd -P)/$(basename "$f")"
        case "$real_f" in
            "${real_extract}"*) ;; # OK
            *) die "Path traversal detected in bundle" ;;
        esac
    done < <(find "$extract_dir" -type f)

    # Find the inner bundle directory (e.g., pd-export-YYYYMMDD-HHMMSS/)
    local bundle_dir
    bundle_dir="$(find "$extract_dir" -maxdepth 1 -mindepth 1 -type d | head -1)"
    if [ -z "$bundle_dir" ]; then
        # Flat layout — files directly in extract_dir
        bundle_dir="$extract_dir"
    fi

    [ -f "$bundle_dir/manifest.json" ] || die "No manifest.json found in bundle"

    local validate_output validate_rc=0
    validate_output="$("$PYTHON" "$MIGRATE_DB" validate "$bundle_dir" 2>/dev/null)" || validate_rc=$?
    if [ $validate_rc -ne 0 ]; then
        if [ $validate_rc -eq 3 ]; then
            echo -e "${RED}Error: Bundle checksum validation failed${NC}" >&2
            exit 3
        else
            die "Bundle validation failed: $validate_output"
        fi
    fi

    local valid
    valid="$(extract_json_field "$validate_output" valid)"
    if [ "$valid" != "True" ]; then
        die "Bundle validation failed: $validate_output"
    fi

    ok "  Bundle validated"

    # ── Step 2: Session check ────────────────────────────────
    step "2/6" "Checking for active sessions"
    if check_active_session; then
        if [ "$FORCE" != "1" ]; then
            echo -e "${RED}Error: Active Claude session detected. Use --force to proceed.${NC}" >&2
            exit 2
        fi
        warn "  Active session detected, proceeding with --force"
    else
        ok "  No active session"
    fi

    # ── Step 3: Create directories ───────────────────────────
    step "3/6" "Creating directories"
    mkdir -p "$ENTITY_DIR"
    ok "  Directories ready"

    # Track summary
    local entity_action="skipped"
    local entity_added=0 entity_skipped=0
    local files_summary=""
    local import_failures=() import_successes=()

    # ── Step 4: Merge/copy entities ──────────────────────────
    step "4/6" "Importing entity data"
    if [ -f "$bundle_dir/entities/entities.db" ]; then
        if [ ! -f "$ENTITY_DB" ]; then
            # Fresh machine — direct copy
            local manifest_ent_count
            manifest_ent_count="$(extract_manifest_count "$bundle_dir/manifest.json" "entities/entities.db" entity_count)"
            if [ -n "$DRY_RUN" ]; then
                entity_added=$manifest_ent_count
                entity_action="would-copy"
                info "  Dry-run: would copy entities.db ($entity_added entities)"
            else
                if cp "$bundle_dir/entities/entities.db" "$ENTITY_DB" 2>/dev/null; then
                    entity_action="copied"
                    entity_added=$manifest_ent_count
                    import_successes+=("entities.db")
                    ok "  Copied entities.db ($entity_added entities)"
                else
                    import_failures+=("entities.db")
                    warn "  Failed to copy entities.db"
                fi
            fi
        else
            # Existing state — merge
            local merge_ent_output
            merge_ent_output="$("$PYTHON" "$MIGRATE_DB" merge-entities "$bundle_dir/entities/entities.db" "$ENTITY_DB" $DRY_RUN 2>/dev/null)"
            entity_added="$(extract_json_field "$merge_ent_output" added)"
            entity_skipped="$(extract_json_field "$merge_ent_output" skipped)"
            if [ -n "$DRY_RUN" ]; then
                entity_action="would-merge"
                info "  Dry-run: would merge $entity_added new, skip $entity_skipped existing"
            else
                entity_action="merged"
                ok "  Merged entities: $entity_added added, $entity_skipped skipped"
            fi
        fi
    else
        info "  No entity data in bundle"
    fi

    # ── Step 5: Copy files ───────────────────────────────────
    step "5/6" "Copying additional files"
    if [ -f "$bundle_dir/projects.txt" ]; then
        if [ -z "$DRY_RUN" ]; then
            if copy_file "$bundle_dir/projects.txt" "$PD_DIR/projects.txt"; then
                files_summary="projects.txt copied"
                ok "  Copied projects.txt"
            else
                files_summary="projects.txt skipped (exists)"
                info "  Skipped projects.txt (exists, use --force to overwrite)"
            fi
        else
            files_summary="projects.txt would be copied"
            info "  Dry-run: would copy projects.txt"
        fi
    else
        files_summary="no additional files"
        info "  No additional files in bundle"
    fi

    # ── Step 6: Verify integrity ─────────────────────────────
    if [ -n "$DRY_RUN" ]; then
        info ""
        ok "Dry-run complete — no changes made"
        info "  Entities: $entity_action ($entity_added entities)"
        return 0
    fi

    step "6/6" "Verifying integrity"
    local verify_errors=0
    verify_imported_db "$ENTITY_DB" entities "entities.db" "$entity_action" "$entity_added"

    # Check for partial failures
    if [ ${#import_failures[@]} -gt 0 ]; then
        echo "" >&2
        echo -e "${RED}Import partially failed${NC}" >&2
        echo -e "  Restored: ${import_successes[*]:-none}" >&2
        echo -e "  Failed: ${import_failures[*]}" >&2
        exit 1
    fi

    # Doctor check (AC-15)
    run_doctor_check

    # Summary
    info ""
    ok "Import complete"
    info "  Entities: $entity_action ($entity_added added, $entity_skipped skipped)"
    [ -n "$files_summary" ] && info "  Files: $files_summary"

    if [ $verify_errors -gt 0 ]; then
        warn "  $verify_errors verification warning(s) — review above"
    fi
    info "  Run your first Claude session to verify MCP servers can connect."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
