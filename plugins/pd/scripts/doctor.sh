#!/usr/bin/env bash
# pd doctor — read-only system health check
# Reports status of prerequisites, plugin environment, memory system, and project context.
# Exit code: 0 if no blockers, 1 if blockers found.
set -euo pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Disable colors when not on a terminal
if [[ ! -t 1 ]]; then
    RED="" GREEN="" YELLOW="" CYAN="" BOLD="" NC=""
fi

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
WARN=0
INFO=0
HAS_BLOCKER=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then echo "macos"
    elif command -v apt &>/dev/null; then echo "debian"
    elif command -v dnf &>/dev/null; then echo "fedora"
    elif command -v pacman &>/dev/null; then echo "arch"
    else echo "unknown"
    fi
}

detect_project_root() {
    local dir="${PWD}"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "${dir}/.git" ]]; then
            echo "$dir"
            return 0
        fi
        dir=$(dirname "$dir")
    done
    echo "${PWD}"
}

# Read a YAML frontmatter field from a .local.md config file.
# Usage: read_config_field <file> <key> <default>
read_config_field() {
    local file="$1" field="$2" default="${3:-}"
    if [[ ! -f "$file" ]]; then
        echo "$default"
        return
    fi
    local value
    value=$(grep "^${field}:" "$file" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ' || echo "")
    if [[ -z "$value" || "$value" == "null" ]]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Print a passing check
pass() {
    printf "  ${GREEN}✓${NC} %s\n" "$1"
    (( PASS++ )) || true
}

# Print a failing (blocker) check with fix instructions
fail() {
    local msg="$1"
    shift
    printf "  ${RED}✗${NC} %s\n" "$msg"
    for fix in "$@"; do
        printf "      ${CYAN}Fix:${NC} %s\n" "$fix"
    done
    (( FAIL++ )) || true
    HAS_BLOCKER=1
}

# Print a warning (non-blocking) with optional fix
warn() {
    local msg="$1"
    shift
    printf "  ${YELLOW}!${NC} %s\n" "$msg"
    for fix in "$@"; do
        printf "      ${CYAN}Fix:${NC} %s\n" "$fix"
    done
    (( WARN++ )) || true
}

# Print an informational note
info() {
    printf "  ${CYAN}i${NC} %s\n" "$1"
    (( INFO++ )) || true
}

# Install command for a package, OS-aware
install_cmd() {
    local pkg="$1"
    local os
    os=$(detect_os)
    case "$os" in
        macos)  echo "brew install $pkg" ;;
        debian) echo "sudo apt install $pkg" ;;
        fedora) echo "sudo dnf install $pkg" ;;
        arch)   echo "sudo pacman -S $pkg" ;;
        *)      echo "<install $pkg using your system package manager>" ;;
    esac
}

# Install command for Python venv module (only needed on some Linux distros)
install_venv_cmd() {
    local os
    os=$(detect_os)
    case "$os" in
        debian) echo "sudo apt install python3-venv" ;;
        fedora) echo "sudo dnf install python3-venv" ;;
        arch)   echo "sudo pacman -S python" ;;
        *)      echo "<install python3-venv using your system package manager>" ;;
    esac
}

# ---------------------------------------------------------------------------
# Project Hygiene helpers (FR-3, FR-4, FR-6b — feature 099)
# ---------------------------------------------------------------------------

# Resolve base branch from pd.local.md or git remote HEAD; fallback main.
# Per design TD + spec FR-3 base-branch resolution.
_pd_resolve_base_branch() {
    local config_file="$1"
    local base
    base=$(read_config_field "${config_file}" "base_branch" "auto")
    if [[ "${base}" == "auto" ]]; then
        base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || true)
        if [[ -z "${base}" ]]; then
            base="main"
        fi
    fi
    printf '%s' "${base}"
}

# ---------------------------------------------------------------------------
# Check functions — each is independently callable for reuse by setup.sh
# ---------------------------------------------------------------------------

check_python3() {
    if ! command -v python3 &>/dev/null; then
        fail "python3 not found" "$(install_cmd python3)"
        return 1
    fi
    local version
    version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    local major minor
    major="${version%%.*}"
    minor="${version#*.}"
    if (( major < 3 || (major == 3 && minor < 12) )); then
        fail "python3 version ${version} < 3.12 required" "$(install_cmd python3)"
        return 1
    fi
    pass "python3 ${version}"
    return 0
}

check_python3_venv() {
    if python3 -c "import venv" 2>/dev/null; then
        pass "python3 venv module available"
        return 0
    fi
    # On macOS, venv is bundled — this only fails on some Linux distros
    if [[ "$(detect_os)" != "macos" ]]; then
        fail "python3 venv module missing" "$(install_venv_cmd)"
        return 1
    fi
    fail "python3 venv module missing" "Reinstall python3: $(install_cmd python3)"
    return 1
}

check_git() {
    if command -v git &>/dev/null; then
        pass "git $(git --version | sed 's/git version //')"
        return 0
    fi
    fail "git not found" "$(install_cmd git)"
    return 1
}

check_rsync() {
    if command -v rsync &>/dev/null; then
        pass "rsync available"
        return 0
    fi
    warn "rsync not found (used by release/sync scripts)" "$(install_cmd rsync)"
    return 1
}

check_timeout() {
    if command -v gtimeout &>/dev/null; then
        pass "gtimeout available (hook timeouts)"
        return 0
    elif command -v timeout &>/dev/null; then
        pass "timeout available (hook timeouts)"
        return 0
    fi
    local os
    os=$(detect_os)
    if [[ "$os" == "macos" ]]; then
        warn "timeout/gtimeout not found (optional, for hook timeouts)" "brew install coreutils"
    else
        warn "timeout not found (optional, for hook timeouts)" "$(install_cmd coreutils)"
    fi
    return 1
}

check_plugin_root() {
    if [[ -d "$PLUGIN_ROOT" ]]; then
        pass "Plugin root: ${PLUGIN_ROOT}"
        return 0
    fi
    fail "Plugin root not found at ${PLUGIN_ROOT}"
    return 1
}

check_venv() {
    if [[ -x "${PLUGIN_ROOT}/.venv/bin/python" ]]; then
        pass "Venv exists at ${PLUGIN_ROOT}/.venv"
        return 0
    fi
    warn "Venv not found at ${PLUGIN_ROOT}/.venv" \
        "python3 -m venv \"${PLUGIN_ROOT}/.venv\""
    return 1
}

check_core_deps() {
    local venv_python="${PLUGIN_ROOT}/.venv/bin/python"
    if [[ ! -x "$venv_python" ]]; then
        warn "Skipping dependency check (no venv)"
        return 1
    fi
    local all_ok=0
    for dep_spec in "mcp:mcp" "numpy:numpy" "dotenv:python-dotenv"; do
        local module="${dep_spec%%:*}"
        local pkg="${dep_spec##*:}"
        if "$venv_python" -c "import ${module}" 2>/dev/null; then
            pass "${pkg} importable"
        else
            warn "${pkg} not importable in venv" \
                "\"${PLUGIN_ROOT}/.venv/bin/pip\" install ${pkg}"
            all_ok=1
        fi
    done
    return "$all_ok"
}

check_semantic_memory() {
    local venv_python="${PLUGIN_ROOT}/.venv/bin/python"
    if [[ ! -x "$venv_python" ]]; then
        warn "Skipping semantic_memory check (no venv)"
        return 1
    fi
    if PYTHONPATH="${PLUGIN_ROOT}/hooks/lib" "$venv_python" -c "import semantic_memory" 2>/dev/null; then
        pass "semantic_memory importable"
        return 0
    fi
    warn "semantic_memory not importable" \
        "Ensure ${PLUGIN_ROOT}/hooks/lib/semantic_memory/ exists"
    return 1
}

check_embedding_provider() {
    local project_root
    project_root=$(detect_project_root)
    local config_file="${project_root}/.claude/pd.local.md"

    local provider
    provider=$(read_config_field "$config_file" "memory_embedding_provider" "")
    local model
    model=$(read_config_field "$config_file" "memory_embedding_model" "")

    if [[ -z "$provider" || "$provider" == "none" ]]; then
        info "No embedding provider configured (keyword-only search)"
        return 0
    fi

    info "Embedding provider: ${provider}${model:+ (model: ${model})}"

    local venv_python="${PLUGIN_ROOT}/.venv/bin/python"
    if [[ ! -x "$venv_python" ]]; then
        warn "Cannot check provider SDK (no venv)"
        return 1
    fi

    # Check SDK importable
    local sdk_module=""
    local sdk_pkg=""
    case "$provider" in
        gemini)  sdk_module="google.genai"; sdk_pkg="google-genai" ;;
        openai)  sdk_module="openai"; sdk_pkg="openai" ;;
        voyage)  sdk_module="voyageai"; sdk_pkg="voyageai" ;;
        ollama)  sdk_module="ollama"; sdk_pkg="ollama" ;;
        *)       info "Unknown provider '${provider}' -- skipping SDK check"; return 0 ;;
    esac

    if "$venv_python" -c "import ${sdk_module}" 2>/dev/null; then
        pass "${sdk_pkg} SDK importable"
    else
        warn "${sdk_pkg} SDK not installed" \
            "\"${PLUGIN_ROOT}/.venv/bin/pip\" install ${sdk_pkg}"
    fi

    # Check API key
    case "$provider" in
        gemini)  _check_api_key "GEMINI_API_KEY" "$project_root" ;;
        openai)  _check_api_key "OPENAI_API_KEY" "$project_root" ;;
        voyage)  _check_api_key "VOYAGE_API_KEY" "$project_root" ;;
        ollama)  _check_ollama ;;
    esac
}

_check_api_key() {
    local key_name="$1"
    local project_root="$2"

    # Check environment variable
    local env_val="${!key_name:-}"
    if [[ -n "$env_val" ]]; then
        local last4="${env_val: -4}"
        pass "${key_name} set in environment (****${last4})"
        return 0
    fi

    # Check .env file at project root
    if [[ -f "${project_root}/.env" ]]; then
        local file_val
        file_val=$(grep "^${key_name}=" "${project_root}/.env" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "")
        # Strip surrounding quotes
        file_val="${file_val#\"}"
        file_val="${file_val%\"}"
        file_val="${file_val#\'}"
        file_val="${file_val%\'}"
        if [[ -n "$file_val" ]]; then
            local last4="${file_val: -4}"
            pass "${key_name} found in .env (****${last4})"
            return 0
        fi
    fi

    warn "${key_name} not found in environment or .env" \
        "Add ${key_name}=<your-key> to ${project_root}/.env"
    return 1
}

_check_ollama() {
    if command -v ollama &>/dev/null; then
        if ollama list &>/dev/null; then
            pass "Ollama server reachable"
            return 0
        fi
        warn "Ollama installed but server not running" \
            "ollama serve"
        return 1
    fi
    warn "Ollama not installed" "$(install_cmd ollama)"
    return 1
}

check_memory_store() {
    local store_dir="$HOME/.claude/pd/memory"
    if [[ -d "$store_dir" ]]; then
        local count
        count=$(find "$store_dir" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
        pass "Global memory store exists (${count} markdown entries)"
    else
        warn "Global memory store not found at ${store_dir}" \
            "mkdir -p \"${store_dir}\""
    fi

    # Check SQLite DB if it exists
    local db_file="${store_dir}/memory.db"
    if [[ -f "$db_file" ]]; then
        if command -v sqlite3 &>/dev/null; then
            local db_count
            db_count=$(sqlite3 "$db_file" "SELECT count(*) FROM entries;" 2>/dev/null || echo "error")
            if [[ "$db_count" == "error" ]]; then
                warn "SQLite DB exists but could not query it"
            else
                pass "SQLite DB accessible (${db_count} entries)"
            fi
        else
            info "SQLite DB exists at ${db_file} (sqlite3 CLI not available for count)"
        fi
    fi
}

check_project_context() {
    local project_root
    project_root=$(detect_project_root)

    if [[ ! -d "${project_root}/.git" ]]; then
        info "Not inside a git project (some checks skipped)"
        return 0
    fi
    pass "Git project: ${project_root}"

    if [[ -d "${project_root}/.claude" ]]; then
        pass ".claude/ directory exists"
    else
        warn ".claude/ directory missing" \
            "mkdir -p \"${project_root}/.claude\""
    fi

    local config_file="${project_root}/.claude/pd.local.md"
    if [[ -f "$config_file" ]]; then
        pass "Config: ${config_file}"
    else
        warn "Config not provisioned" \
            "cp \"${PLUGIN_ROOT}/templates/config.local.md\" \"${config_file}\""
    fi

    local artifacts_root
    artifacts_root=$(read_config_field "$config_file" "artifacts_root" "docs")
    if [[ -d "${project_root}/${artifacts_root}" ]]; then
        pass "Artifacts directory: ${artifacts_root}/"
    else
        warn "Artifacts directory ${artifacts_root}/ missing" \
            "mkdir -p \"${project_root}/${artifacts_root}\""
    fi
}

# ---------------------------------------------------------------------------
# Project Hygiene checks (feature 099 — FR-3, FR-4, FR-6b)
# ---------------------------------------------------------------------------

# FR-3: Detect orphan feature branches.
check_stale_feature_branches() {
    local project_root config_file artifacts_root base_branch
    project_root=$(detect_project_root)

    if [[ ! -d "${project_root}/.git" ]]; then
        return 0  # Skip silently if not a git project.
    fi

    config_file="${project_root}/.claude/pd.local.md"
    artifacts_root=$(read_config_field "${config_file}" "artifacts_root" "docs")
    base_branch=$(_pd_resolve_base_branch "${config_file}")

    local n_warn=0 n_info=0 n_total=0
    local branches
    branches=$(cd "${project_root}" && git for-each-ref --format='%(refname:short)' 'refs/heads/feature/*' 2>/dev/null || true)

    if [[ -z "${branches}" ]]; then
        pass "No feature branches"
        return 0
    fi

    while IFS= read -r branch; do
        [[ -z "${branch}" ]] && continue
        (( n_total++ )) || true
        # Parse feature ID and slug.
        if [[ ! "${branch}" =~ ^feature/([0-9]+)-([a-z0-9-]+)$ ]]; then
            info "Branch ${branch}: no parsable feature ID — manual classification needed"
            (( n_info++ )) || true
            continue
        fi
        local id="${BASH_REMATCH[1]}"
        local slug="${BASH_REMATCH[2]}"
        local meta_path="${project_root}/${artifacts_root}/features/${id}-${slug}/.meta.json"

        # Read status from .meta.json (filesystem read; no MCP dependency).
        local status="no entity"
        if [[ -f "${meta_path}" ]]; then
            status=$(grep -oE '"status"[[:space:]]*:[[:space:]]*"[^"]+"' "${meta_path}" 2>/dev/null | head -1 | sed -E 's/.*"([^"]+)"$/\1/' || echo "unknown")
            [[ -z "${status}" ]] && status="unknown"
        fi

        # Merge-state short-circuit (highest priority): silent if merged.
        local merged=false
        if (cd "${project_root}" && git merge-base --is-ancestor "${branch}" "${base_branch}" 2>/dev/null); then
            merged=true
        fi
        if [[ "${merged}" == "true" ]]; then
            continue  # silent
        fi

        # Active states → silent.
        case "${status}" in
            active|planned|paused|in_progress)
                continue
                ;;
            completed|cancelled|abandoned|archived)
                # Tier 1: warn with cleanup hint.
                warn "Orphan branch: ${branch} (status=${status}, unmerged into ${base_branch})" \
                    "git branch -D ${branch}  # if no longer needed"
                (( n_warn++ )) || true
                ;;
            *)
                # Tier 2 (no entity / unknown): info, non-destructive.
                info "Branch ${branch} has no entity record (status=${status}, unmerged into ${base_branch}) — register via /pd:brainstorm or delete if abandoned"
                (( n_info++ )) || true
                ;;
        esac
    done <<< "${branches}"

    if (( n_warn == 0 && n_info == 0 )); then
        pass "No stale feature branches (${n_total} examined)"
    fi
}

# FR-4: Detect tier docs whose source content has drifted past the staleness threshold.
check_tier_doc_freshness() {
    local project_root config_file
    project_root=$(detect_project_root)

    if [[ ! -d "${project_root}/.git" ]]; then
        return 0
    fi

    config_file="${project_root}/.claude/pd.local.md"
    local threshold doc_root
    threshold=$(read_config_field "${config_file}" "tier_doc_staleness_days" "30")
    doc_root=$(read_config_field "${config_file}" "tier_doc_root" "docs")

    # Default tier source paths (per finish-feature.md Step 2b convention).
    local tiers=("user-guide" "dev-guide" "technical")
    local default_user_guide="README.md package.json setup.py pyproject.toml bin/"
    local default_dev_guide="src/ test/ Makefile .github/ CONTRIBUTING.md docker-compose.yml"
    local default_technical="src/ docs/technical/"

    local found_any=false
    for tier in "${tiers[@]}"; do
        local tier_underscored="${tier//-/_}"
        local default_paths
        case "${tier}" in
            user-guide) default_paths="${default_user_guide}" ;;
            dev-guide) default_paths="${default_dev_guide}" ;;
            technical) default_paths="${default_technical}" ;;
        esac
        local source_paths
        source_paths=$(read_config_field "${config_file}" "tier_doc_source_paths_${tier_underscored}" "${default_paths}")

        local tier_glob="${project_root}/${doc_root}/${tier}"
        if [[ ! -d "${tier_glob}" ]]; then
            info "No docs in tier ${tier}"
            continue
        fi

        for doc in "${tier_glob}"/*.md; do
            [[ -f "${doc}" ]] || continue
            found_any=true
            # Awk-extract last-updated frontmatter (no PyYAML).
            local last_updated
            last_updated=$(awk '/^---$/{c++;next} c==1 && /^last-updated:/{sub(/^last-updated:[[:space:]]*/, ""); print; exit}' "${doc}" 2>/dev/null || echo "")
            if [[ -z "${last_updated}" ]]; then
                info "Skipped: ${doc##*/} (no last-updated frontmatter)"
                continue
            fi

            # Source ts via git log (multi-path).
            local source_ts
            source_ts=$(cd "${project_root}" && git log -1 --format=%aI -- ${source_paths} 2>/dev/null || echo "")
            if [[ -z "${source_ts}" ]]; then
                info "Skipped: ${doc##*/} (tier ${tier}: no source commits)"
                continue
            fi

            # Date diff via python3 stdlib datetime.
            local gap_days
            gap_days=$(python3 -c "
from datetime import datetime
import sys
try:
    src = datetime.fromisoformat(sys.argv[1].replace('Z', '+00:00'))
    upd = datetime.fromisoformat(sys.argv[2].replace('Z', '+00:00'))
    print(int((src - upd).total_seconds() // 86400))
except Exception:
    print('')
" "${source_ts}" "${last_updated}" 2>/dev/null || echo "")

            if [[ -z "${gap_days}" ]]; then
                info "Skipped: ${doc##*/} (tier ${tier}: timestamp parse failed)"
                continue
            fi

            if (( gap_days > threshold )); then
                warn "Tier doc stale: ${doc##*/} (last-updated ${last_updated}, source modified ${gap_days}d later)"
            fi
        done
    done

    if [[ "${found_any}" == "false" ]]; then
        info "Tier doc freshness: no tier docs found (skipped)"
    fi
}

# FR-6b: Active backlog size threshold check.
check_active_backlog_size() {
    local project_root config_file backlog_path threshold count script_dir
    project_root=$(detect_project_root)
    config_file="${project_root}/.claude/pd.local.md"
    backlog_path="${project_root}/$(read_config_field "${config_file}" "artifacts_root" "docs")/backlog.md"
    threshold=$(read_config_field "${config_file}" "backlog_active_threshold" "30")

    if [[ ! -f "${backlog_path}" ]]; then
        info "Active backlog: no backlog.md found"
        return 0
    fi

    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ ! -f "${script_dir}/cleanup_backlog.py" ]]; then
        info "Active backlog: cleanup_backlog.py not found (skipped)"
        return 0
    fi

    count=$(python3 "${script_dir}/cleanup_backlog.py" --count-active --backlog-path "${backlog_path}" 2>/dev/null || echo 0)
    # Coerce empty / non-numeric to 0.
    [[ "${count}" =~ ^[0-9]+$ ]] || count=0

    if (( count > threshold )); then
        warn "Active backlog: ${count} items (threshold ${threshold})" \
            "Run /pd:cleanup-backlog to archive closed sections"
    else
        pass "Active backlog: ${count} items"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
run_all_checks() {
    printf "\n${BOLD}pd doctor${NC}\n"
    printf "═══════════════════════════════════════════════════════════════\n"

    printf "\n${BOLD}System Prerequisites${NC}\n"
    check_python3 || true
    check_python3_venv || true
    check_git || true
    check_rsync || true
    check_timeout || true

    printf "\n${BOLD}Plugin Environment${NC}\n"
    check_plugin_root || true
    check_venv || true
    check_core_deps || true
    check_semantic_memory || true

    printf "\n${BOLD}Embedding Provider${NC}\n"
    check_embedding_provider || true

    printf "\n${BOLD}Memory System${NC}\n"
    check_memory_store || true

    printf "\n${BOLD}Project Hygiene${NC}\n"
    check_stale_feature_branches || true
    check_tier_doc_freshness || true
    check_active_backlog_size || true

    printf "\n${BOLD}Project Context${NC}\n"
    check_project_context || true

    printf "\n═══════════════════════════════════════════════════════════════\n"
    local total=$(( PASS + FAIL + WARN + INFO ))
    printf "${BOLD}Summary:${NC} "
    printf "${GREEN}${PASS}/${total} passed${NC}"
    if (( FAIL > 0 )); then
        printf ", ${RED}${FAIL} blocker(s)${NC}"
    fi
    if (( WARN > 0 )); then
        printf ", ${YELLOW}${WARN} fixable${NC}"
    fi
    if (( INFO > 0 )); then
        printf ", ${CYAN}${INFO} informational${NC}"
    fi
    printf "\n\n"

    if (( HAS_BLOCKER )); then
        printf "${RED}Blockers found — resolve them before using pd.${NC}\n\n"
        return 1
    fi
    if (( WARN > 0 )); then
        printf "${YELLOW}Some optional components need attention.${NC}\n"
        printf "Run ${CYAN}${PLUGIN_ROOT}/scripts/setup.sh${NC} to fix automatically.\n\n"
    else
        printf "${GREEN}All clear.${NC}\n\n"
    fi
    return 0
}

# Allow sourcing without executing (for setup.sh reuse)
if [[ "${BASH_SOURCE[0]:-$0}" == "${0}" ]]; then
    run_all_checks
fi
