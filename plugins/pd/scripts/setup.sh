#!/usr/bin/env bash
# pd setup — interactive installer
# Runs doctor checks, then fixes fixable issues step by step.
# Idempotent: safe to re-run at any time.
set -euo pipefail

# ---------------------------------------------------------------------------
# Bootstrap: source doctor.sh for all check functions and helpers
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/doctor.sh"

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------
AUTO_YES=0

step_header() {
    local step="$1" title="$2"
    printf "\n${BOLD}[${step}] ${title}${NC}\n"
    printf "───────────────────────────────────────────────────────────────\n"
}

ask_continue() {
    local prompt="${1:-Continue?}"
    if (( AUTO_YES )); then return 0; fi
    local reply
    read -rp "$(printf "${YELLOW}${prompt} (y/n): ${NC}")" reply
    case "$reply" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# [1/7] Diagnostics
# ---------------------------------------------------------------------------
step_diagnostics() {
    step_header "1/4" "Running diagnostics..."

    # Reset counters before running checks
    PASS=0 FAIL=0 WARN=0 INFO=0 HAS_BLOCKER=0

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

    printf "\n${BOLD}Project Context${NC}\n"
    check_project_context || true

    printf "\n"

    if (( HAS_BLOCKER )); then
        printf "${RED}Blockers detected. Resolve these before continuing:${NC}\n"
        printf "  - Install missing system prerequisites listed above.\n"
        printf "  - Then re-run this script.\n\n"
        exit 1
    fi

    if (( WARN > 0 )); then
        printf "${YELLOW}${WARN} fixable issue(s) found.${NC}\n"
        if ! ask_continue "Continue with setup?"; then
            printf "Aborted.\n"
            exit 0
        fi
    else
        printf "${GREEN}No issues found. Running setup for completeness...${NC}\n"
    fi
}

# ---------------------------------------------------------------------------
# [2/7] Create/verify venv
# ---------------------------------------------------------------------------
step_venv() {
    step_header "2/4" "Create/verify venv"

    if [[ -x "${PLUGIN_ROOT}/.venv/bin/python" ]]; then
        printf "  Venv already exists at ${PLUGIN_ROOT}/.venv, skipping creation.\n"
    else
        printf "  Creating venv at ${PLUGIN_ROOT}/.venv...\n"
        if ! python3 -m venv "${PLUGIN_ROOT}/.venv" 2>&1; then
            printf "  ${RED}Failed to create venv.${NC}\n"
            printf "  ${CYAN}Fix:${NC} $(install_venv_cmd)\n"
            exit 1
        fi
        printf "  ${GREEN}Venv created.${NC}\n"
    fi

    printf "  Upgrading pip...\n"
    "${PLUGIN_ROOT}/.venv/bin/pip" install --quiet --upgrade pip
    printf "  Installing core dependencies...\n"
    "${PLUGIN_ROOT}/.venv/bin/pip" install --quiet --upgrade "mcp>=1.0,<2" numpy python-dotenv
    printf "  ${GREEN}Core dependencies installed.${NC}\n"
}

# ---------------------------------------------------------------------------
# [3/4] Initialize project
# ---------------------------------------------------------------------------
step_init_project() {
    step_header "3/4" "Initialize project"

    # Project-level setup (only if inside a git repo)
    local project_root
    project_root=$(detect_project_root)

    if [[ ! -d "${project_root}/.git" ]]; then
        printf "  Not inside a git project — skipping project-level setup.\n"
        return
    fi

    # Create .claude/ directory
    if [[ ! -d "${project_root}/.claude" ]]; then
        mkdir -p "${project_root}/.claude"
        printf "  ${GREEN}Created ${project_root}/.claude/${NC}\n"
    else
        printf "  .claude/ directory already exists.\n"
    fi

    # Copy config template
    local config_file="${project_root}/.claude/pd.local.md"
    local template="${PLUGIN_ROOT}/templates/config.local.md"
    if [[ -f "$config_file" ]]; then
        printf "  Config already provisioned at ${config_file}\n"
    elif [[ -f "$template" ]]; then
        cp "$template" "$config_file"
        printf "  ${GREEN}Copied config template to ${config_file}${NC}\n"
    else
        printf "  ${YELLOW}Config template not found at ${template}${NC}\n"
    fi
}

# ---------------------------------------------------------------------------
# [7/7] Final health check
# ---------------------------------------------------------------------------
step_final_check() {
    step_header "4/4" "Final health check"

    # Reset counters for clean final tally
    PASS=0 FAIL=0 WARN=0 INFO=0 HAS_BLOCKER=0

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
        printf "${RED}Some blockers remain. Please fix them manually.${NC}\n\n"
    elif (( WARN > 0 )); then
        printf "${YELLOW}Some optional issues remain. Re-run setup to address them.${NC}\n\n"
    else
        printf "${GREEN}Setup complete. pd is ready.${NC}\n\n"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--yes) AUTO_YES=1; shift ;;
            *) printf "${RED}Unknown option: $1${NC}\n"; exit 1 ;;
        esac
    done

    printf "\n${BOLD}pd setup${NC}\n"
    if (( AUTO_YES )); then
        printf "${CYAN}(non-interactive mode)${NC}\n"
    fi
    printf "═══════════════════════════════════════════════════════════════\n"

    step_diagnostics
    step_venv
    step_init_project
    step_final_check
}

main "$@"
