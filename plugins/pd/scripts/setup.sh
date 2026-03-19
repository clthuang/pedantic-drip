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
    step_header "1/7" "Running diagnostics..."

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
    check_semantic_memory || true

    printf "\n${BOLD}Embedding Provider${NC}\n"
    check_embedding_provider || true

    printf "\n${BOLD}Memory System${NC}\n"
    check_memory_store || true

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
    step_header "2/7" "Create/verify venv"

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
# [3/7] Choose embedding provider
# ---------------------------------------------------------------------------
CHOSEN_PROVIDER=""
CHOSEN_KEY_NAME=""

step_choose_provider() {
    step_header "3/7" "Choose embedding provider"

    if (( AUTO_YES )); then
        CHOSEN_PROVIDER="none"
        CHOSEN_KEY_NAME=""
        printf "  Non-interactive mode: defaulting to ${BOLD}none${NC} (keyword-only search).\n"
        return
    fi

    printf "\n  Select embedding provider:\n"
    printf "    ${BOLD}1)${NC} gemini  -- Google Gemini (free tier, needs GEMINI_API_KEY)\n"
    printf "    ${BOLD}2)${NC} openai  -- OpenAI (needs OPENAI_API_KEY)\n"
    printf "    ${BOLD}3)${NC} voyage  -- Voyage AI (needs VOYAGE_API_KEY)\n"
    printf "    ${BOLD}4)${NC} ollama  -- Local Ollama (no key, needs local server)\n"
    printf "    ${BOLD}5)${NC} none    -- Skip (keyword-only search)\n\n"

    local choice
    read -rp "$(printf "  ${CYAN}Choice [1-5]: ${NC}")" choice

    case "$choice" in
        1) CHOSEN_PROVIDER="gemini";  CHOSEN_KEY_NAME="GEMINI_API_KEY" ;;
        2) CHOSEN_PROVIDER="openai";  CHOSEN_KEY_NAME="OPENAI_API_KEY" ;;
        3) CHOSEN_PROVIDER="voyage";  CHOSEN_KEY_NAME="VOYAGE_API_KEY" ;;
        4) CHOSEN_PROVIDER="ollama";  CHOSEN_KEY_NAME="" ;;
        5) CHOSEN_PROVIDER="none";    CHOSEN_KEY_NAME="" ;;
        *)
            printf "  ${YELLOW}Invalid choice, defaulting to none.${NC}\n"
            CHOSEN_PROVIDER="none"
            CHOSEN_KEY_NAME=""
            ;;
    esac

    printf "  Selected: ${BOLD}${CHOSEN_PROVIDER}${NC}\n"
}

# ---------------------------------------------------------------------------
# [4/7] Install provider SDK + prompt for API key
# ---------------------------------------------------------------------------
COLLECTED_API_KEY=""

step_install_provider() {
    step_header "4/7" "Install provider SDK"

    local pip="${PLUGIN_ROOT}/.venv/bin/pip"

    case "$CHOSEN_PROVIDER" in
        gemini)
            printf "  Installing google-genai SDK...\n"
            "$pip" install --quiet --upgrade "google-genai>=1.0,<2"
            printf "  ${GREEN}google-genai installed.${NC}\n"
            _prompt_api_key "GEMINI_API_KEY"
            ;;
        openai)
            printf "  Installing openai SDK...\n"
            "$pip" install --quiet --upgrade openai
            printf "  ${GREEN}openai installed.${NC}\n"
            _prompt_api_key "OPENAI_API_KEY"
            ;;
        voyage)
            printf "  Installing voyageai SDK...\n"
            "$pip" install --quiet --upgrade voyageai
            printf "  ${GREEN}voyageai installed.${NC}\n"
            _prompt_api_key "VOYAGE_API_KEY"
            ;;
        ollama)
            printf "  Installing ollama SDK...\n"
            "$pip" install --quiet --upgrade ollama
            printf "  ${GREEN}ollama SDK installed.${NC}\n"
            printf "\n  ${CYAN}Ollama setup:${NC}\n"
            printf "    1. Install Ollama:       https://ollama.com/download\n"
            printf "    2. Start the server:     ollama serve\n"
            printf "    3. Pull a model:         ollama pull nomic-embed-text\n"
            ;;
        none)
            printf "  Skipping provider installation.\n"
            ;;
    esac
}

_prompt_api_key() {
    local key_name="$1"
    COLLECTED_API_KEY=""

    if (( AUTO_YES )); then
        printf "  Non-interactive mode: skipping ${key_name} prompt.\n"
        return
    fi

    # Check environment
    local env_val="${!key_name:-}"
    if [[ -n "$env_val" ]]; then
        local last4="${env_val: -4}"
        printf "  ${GREEN}${key_name} already set in environment (****${last4}).${NC}\n"
        return
    fi

    # Check .env at project root
    local project_root
    project_root=$(detect_project_root)
    if [[ -f "${project_root}/.env" ]]; then
        local file_val
        file_val=$(grep "^${key_name}=" "${project_root}/.env" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "")
        file_val="${file_val#\"}"
        file_val="${file_val%\"}"
        file_val="${file_val#\'}"
        file_val="${file_val%\'}"
        if [[ -n "$file_val" ]]; then
            local last4="${file_val: -4}"
            printf "  ${GREEN}${key_name} found in .env (****${last4}).${NC}\n"
            return
        fi
    fi

    printf "\n  ${key_name} not found.\n"
    local key_val
    read -rp "$(printf "  ${CYAN}Enter ${key_name} (or press Enter to skip): ${NC}")" key_val
    if [[ -n "$key_val" ]]; then
        COLLECTED_API_KEY="$key_val"
        local last4="${key_val: -4}"
        printf "  ${GREEN}Key captured (****${last4}). Will write in next step.${NC}\n"
    else
        printf "  ${YELLOW}Skipped. You can add it later to your .env file.${NC}\n"
    fi
}

# ---------------------------------------------------------------------------
# [5/7] Configure environment
# ---------------------------------------------------------------------------
step_configure_env() {
    step_header "5/7" "Configure environment"

    local project_root
    project_root=$(detect_project_root)

    # Write API key if we collected one
    # Uses awk instead of sed to avoid delimiter issues with special characters in keys (/+&\)
    if [[ -n "$COLLECTED_API_KEY" && -n "$CHOSEN_KEY_NAME" ]]; then
        local env_file="${project_root}/.env"
        if [[ -f "$env_file" ]]; then
            local tmp="${env_file}.tmp.$$"
            awk -v key="$CHOSEN_KEY_NAME" -v val="$COLLECTED_API_KEY" '
                BEGIN {found=0}
                $0 ~ "^"key"=" {print key"="val; found=1; next}
                {print}
                END {if(!found) print key"="val}
            ' "$env_file" > "$tmp"
            mv "$tmp" "$env_file"
            printf "  Updated/added ${CHOSEN_KEY_NAME} in ${env_file}\n"
        else
            printf "%s=%s\n" "$CHOSEN_KEY_NAME" "$COLLECTED_API_KEY" > "$env_file"
            printf "  Created ${env_file} with ${CHOSEN_KEY_NAME}\n"
        fi
        printf "  ${GREEN}Wrote ${CHOSEN_KEY_NAME} to ${env_file}${NC}\n"
    else
        printf "  No API key to write.\n"
    fi

    # Update config with chosen provider if applicable
    local config_file="${project_root}/.claude/pd.local.md"
    if [[ -f "$config_file" && "$CHOSEN_PROVIDER" != "none" && -n "$CHOSEN_PROVIDER" ]]; then
        local current_provider
        current_provider=$(read_config_field "$config_file" "memory_embedding_provider" "")
        if [[ "$current_provider" != "$CHOSEN_PROVIDER" ]]; then
            if grep -q "^memory_embedding_provider:" "$config_file" 2>/dev/null; then
                local tmp="${config_file}.tmp.$$"
                awk -v key="memory_embedding_provider" -v val="$CHOSEN_PROVIDER" \
                    '$0 ~ "^"key":" {$0=key": "val} {print}' "$config_file" > "$tmp"
                mv "$tmp" "$config_file"
            fi
            printf "  Updated embedding provider to ${CHOSEN_PROVIDER} in config.\n"

            # Update model for known providers
            local default_model=""
            case "$CHOSEN_PROVIDER" in
                gemini)  default_model="gemini-embedding-001" ;;
                openai)  default_model="text-embedding-3-small" ;;
                voyage)  default_model="voyage-3-lite" ;;
                ollama)  default_model="nomic-embed-text" ;;
            esac
            if [[ -n "$default_model" ]] && grep -q "^memory_embedding_model:" "$config_file" 2>/dev/null; then
                local tmp="${config_file}.tmp.$$"
                awk -v key="memory_embedding_model" -v val="$default_model" \
                    '$0 ~ "^"key":" {$0=key": "val} {print}' "$config_file" > "$tmp"
                mv "$tmp" "$config_file"
                printf "  Updated embedding model to ${default_model} in config.\n"
            fi
        else
            printf "  Provider already set to ${CHOSEN_PROVIDER} in config.\n"
        fi
    fi
}

# ---------------------------------------------------------------------------
# [6/7] Initialize project
# ---------------------------------------------------------------------------
step_init_project() {
    step_header "6/7" "Initialize project"

    # Global memory store
    local store_dir="$HOME/.claude/pd/memory"
    if [[ -d "$store_dir" ]]; then
        printf "  Global memory store already exists.\n"
    else
        mkdir -p "$store_dir"
        printf "  ${GREEN}Created ${store_dir}${NC}\n"
    fi

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
    step_header "7/7" "Final health check"

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
    check_semantic_memory || true

    printf "\n${BOLD}Embedding Provider${NC}\n"
    check_embedding_provider || true

    printf "\n${BOLD}Memory System${NC}\n"
    check_memory_store || true

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
    step_choose_provider
    step_install_provider
    step_configure_env
    step_init_project
    step_final_check
}

main "$@"
