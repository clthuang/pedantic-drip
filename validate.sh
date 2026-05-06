#!/bin/bash
# Validation script for agent-teams repository
# Validates skills, agents, plugins, and commands

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

log_error() {
    echo -e "${RED}ERROR: $1${NC}"
    ((ERRORS++)) || true
}

log_warning() {
    echo -e "${YELLOW}WARNING: $1${NC}"
    ((WARNINGS++)) || true
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_info() {
    echo -e "  $1"
}

# Validate YAML frontmatter
validate_frontmatter() {
    local file=$1
    local content=$(cat "$file")

    # Check for frontmatter markers
    if ! echo "$content" | head -1 | grep -q "^---$"; then
        log_error "$file: Missing opening frontmatter marker (---)"
        return 1
    fi

    # Extract frontmatter
    local frontmatter=$(echo "$content" | sed -n '/^---$/,/^---$/p' | sed '1d;$d')

    # Check for name field
    if ! echo "$frontmatter" | grep -q "^name:"; then
        log_error "$file: Missing 'name' field in frontmatter"
        return 1
    fi

    # Check for description field
    if ! echo "$frontmatter" | grep -q "^description:"; then
        log_error "$file: Missing 'description' field in frontmatter"
        return 1
    fi

    # Validate name format (lowercase, hyphens only)
    local name=$(echo "$frontmatter" | grep "^name:" | sed 's/^name:[[:space:]]*//')
    if ! echo "$name" | grep -qE "^[a-z][a-z0-9-]*$"; then
        log_error "$file: Name '$name' must be lowercase with hyphens only"
        return 1
    fi

    return 0
}

# Validate skill description quality
validate_description() {
    local file=$1
    local content=$(cat "$file")
    local frontmatter=$(echo "$content" | sed -n '/^---$/,/^---$/p' | sed '1d;$d')
    local description=$(echo "$frontmatter" | grep "^description:" | sed 's/^description:[[:space:]]*//')

    # Check minimum length
    if [ ${#description} -lt 50 ]; then
        log_warning "$file: Description is short (<50 chars). Consider adding more detail."
    fi

    # Check for "Use when" pattern
    if ! echo "$description" | grep -qi "use when\|use for\|triggered when"; then
        log_warning "$file: Description should include when to use it (e.g., 'Use when...')"
    fi

    # Check for first-person language
    if echo "$description" | grep -qiE "^(I |You can|This lets you)"; then
        log_warning "$file: Description should be third-person (e.g., 'Creates...' not 'You can create...')"
    fi
}

# Validate SKILL.md line count
validate_skill_size() {
    local file=$1
    local lines=$(wc -l < "$file")

    if [ "$lines" -gt 500 ]; then
        log_warning "$file: SKILL.md has $lines lines (recommended <500). Consider using reference files."
    fi
}

# Validate agent-specific fields (model, color, example blocks)
validate_agent_fields() {
    local file=$1
    local content=$(cat "$file")
    local frontmatter=$(echo "$content" | sed -n '/^---$/,/^---$/p' | sed '1d;$d')

    # Check model field
    if echo "$frontmatter" | grep -q "^model:"; then
        local model=$(echo "$frontmatter" | grep "^model:" | sed 's/^model:[[:space:]]*//')
        if ! echo "$model" | grep -qE "^[a-zA-Z0-9_\.\/-]+$"; then
            log_error "$file: Invalid model '$model' (must be alphanumeric with hyphens, underscores, dots, or slashes)"
        fi
    else
        log_warning "$file: Missing 'model' field (defaults to inherit)"
    fi

    # Check color field
    if echo "$frontmatter" | grep -q "^color:"; then
        local color=$(echo "$frontmatter" | grep "^color:" | sed 's/^color:[[:space:]]*//')
        if ! echo "blue cyan green yellow magenta red" | grep -qw "$color"; then
            log_error "$file: Invalid color '$color' (must be blue, cyan, green, yellow, magenta, or red)"
        fi
    else
        log_warning "$file: Missing 'color' field (recommended for UI differentiation)"
    fi

    # Check for example blocks in description (best practice for reliable triggering)
    local description=$(echo "$content" | sed -n '/^---$/,/^---$/p' | sed '1d;$d' | grep "^description:")
    if ! grep -q "<example>" "$file"; then
        log_warning "$file: No <example> blocks found (recommended for reliable agent triggering)"
    fi

    # Error on YAML examples: in frontmatter (must use XML <example> blocks only)
    if echo "$frontmatter" | grep -q "^examples:"; then
        log_error "$file: YAML 'examples:' in frontmatter — must use XML <example> blocks in body instead"
    fi

    # Warn on non-canonical frontmatter field order (name → description → model → tools → color)
    local field_order=""
    while IFS= read -r line; do
        local key=$(echo "$line" | sed -n 's/^\([a-z_-]*\):.*/\1/p')
        [ -n "$key" ] && field_order="$field_order $key"
    done <<< "$frontmatter"
    local canonical=" name description model tools color"
    # Extract only canonical fields in the order they appear
    local actual_order=""
    for f in $field_order; do
        case "$f" in
            name|description|model|tools|color) actual_order="$actual_order $f" ;;
        esac
    done
    local expected_order=""
    for f in $canonical; do
        # Only include fields that actually exist
        if echo "$actual_order" | grep -qw "$f"; then
            expected_order="$expected_order $f"
        fi
    done
    if [ "$actual_order" != "$expected_order" ]; then
        log_warning "$file: Non-canonical frontmatter field order (expected:$expected_order, got:$actual_order)"
    fi
}

# Validate hooks.json schema (event names, structure, portability)
validate_hooks_schema() {
    local file=$1
    local valid_events="PreToolUse PostToolUse PostToolUseFailure UserPromptSubmit Stop SubagentStop SessionStart SessionEnd PreCompact Notification"

    # Check top-level structure has "hooks" key
    if ! jq -e '.hooks' "$file" > /dev/null 2>&1; then
        log_error "$file: Missing top-level 'hooks' key"
        return 1
    fi

    # Validate event names
    local events=$(jq -r '.hooks | keys[]' "$file" 2>/dev/null)
    while IFS= read -r event; do
        [ -z "$event" ] && continue
        if ! echo "$valid_events" | grep -qw "$event"; then
            log_error "$file: Invalid event name '$event' (valid: $valid_events)"
        fi
    done <<< "$events"

    # Validate each event's hook entries
    local event_count=$(jq '.hooks | keys | length' "$file" 2>/dev/null)
    for (( i=0; i<event_count; i++ )); do
        local event_name=$(jq -r ".hooks | keys[$i]" "$file")
        local entry_count=$(jq ".hooks[\"$event_name\"] | length" "$file" 2>/dev/null)

        for (( j=0; j<entry_count; j++ )); do
            local entry_path=".hooks[\"$event_name\"][$j]"

            # Check matcher field (not required for Stop/SubagentStop/UserPromptSubmit events)
            # UserPromptSubmit fires on every prompt; matcher is optional per CC hook docs.
            if [[ "$event_name" != "Stop" ]] && [[ "$event_name" != "SubagentStop" ]] && [[ "$event_name" != "UserPromptSubmit" ]]; then
                if ! jq -e "$entry_path.matcher" "$file" > /dev/null 2>&1; then
                    log_error "$file: $event_name[$j] missing 'matcher' field"
                fi
            fi

            # Check hooks array
            if ! jq -e "$entry_path.hooks" "$file" > /dev/null 2>&1; then
                log_error "$file: $event_name[$j] missing 'hooks' array"
                continue
            fi

            local hook_count=$(jq "$entry_path.hooks | length" "$file" 2>/dev/null)
            for (( k=0; k<hook_count; k++ )); do
                local hook_path="$entry_path.hooks[$k]"
                local hook_type=$(jq -r "$hook_path.type // empty" "$file")

                # Check type field
                if [ -z "$hook_type" ]; then
                    log_error "$file: $event_name[$j].hooks[$k] missing 'type' field"
                elif [ "$hook_type" != "command" ] && [ "$hook_type" != "prompt" ]; then
                    log_error "$file: $event_name[$j].hooks[$k] invalid type '$hook_type' (must be 'command' or 'prompt')"
                fi

                # Check type-specific required fields
                if [ "$hook_type" = "command" ]; then
                    if ! jq -e "$hook_path.command" "$file" > /dev/null 2>&1; then
                        log_error "$file: $event_name[$j].hooks[$k] type 'command' missing 'command' field"
                    else
                        local cmd=$(jq -r "$hook_path.command" "$file")
                        if [[ "$cmd" != *'${CLAUDE_PLUGIN_ROOT}'* ]] && [[ "$cmd" == *"/"* ]]; then
                            log_warning "$file: $event_name[$j].hooks[$k] command uses hardcoded path — consider \${CLAUDE_PLUGIN_ROOT} for portability"
                        fi
                    fi
                elif [ "$hook_type" = "prompt" ]; then
                    if ! jq -e "$hook_path.prompt" "$file" > /dev/null 2>&1; then
                        log_error "$file: $event_name[$j].hooks[$k] type 'prompt' missing 'prompt' field"
                    fi
                fi
            done
        done
    done

    return 0
}

# Validate .claude-plugin/ directory structure
validate_plugin_dir_structure() {
    local plugin_dir=$1
    local allowed_files="plugin.json marketplace.json"

    while IFS= read -r file_in_dir; do
        [ -z "$file_in_dir" ] && continue
        local basename=$(basename "$file_in_dir")
        if ! echo "$allowed_files" | grep -qw "$basename"; then
            log_warning "$plugin_dir: Unexpected file '$basename' — .claude-plugin/ should only contain plugin.json and marketplace.json"
        fi
    done < <(find "$plugin_dir" -maxdepth 1 -type f 2>/dev/null)
}

# Validate command frontmatter details (description length, allowed-tools)
validate_command_frontmatter() {
    local file=$1
    local frontmatter=$2

    # Check description length (appears in /help output, should be concise)
    if echo "$frontmatter" | grep -q "^description:"; then
        local desc=$(echo "$frontmatter" | grep "^description:" | sed 's/^description:[[:space:]]*//')
        if [ ${#desc} -gt 80 ]; then
            log_warning "$file: Command description is ${#desc} chars (recommended <=80 for /help output)"
        fi
    fi

    # Check allowed-tools format if present
    if echo "$frontmatter" | grep -q "^allowed-tools:"; then
        local tools_value=$(echo "$frontmatter" | grep "^allowed-tools:" | sed 's/^allowed-tools:[[:space:]]*//')
        # Should be a YAML list or comma-separated — warn if it looks like a single unquoted word with spaces
        if [[ "$tools_value" != "["* ]] && [[ "$tools_value" == *" "* ]] && [[ "$tools_value" != *","* ]]; then
            log_warning "$file: 'allowed-tools' format may be incorrect — use comma-separated values or YAML list"
        fi
    fi
}

# Validate plugin.json
validate_plugin_json() {
    local file=$1

    # Check JSON syntax
    if ! jq empty "$file" 2>/dev/null; then
        log_error "$file: Invalid JSON syntax"
        return 1
    fi

    # Check required fields (only 'name' is required per official docs)
    if ! jq -e '.name' "$file" > /dev/null 2>&1; then
        log_error "$file: Missing required 'name' field"
        return 1
    fi

    # Validate name format (kebab-case)
    local name=$(jq -r '.name' "$file")
    if ! echo "$name" | grep -qE "^[a-z][a-z0-9-]*$"; then
        log_error "$file: Name '$name' must be kebab-case (lowercase with hyphens)"
        return 1
    fi

    # Validate version format: X.Y.Z or X.Y.Z-dev
    local version=$(jq -r '.version // empty' "$file")
    if [ -n "$version" ]; then
        if ! echo "$version" | grep -qE "^[0-9]+\.[0-9]+\.[0-9]+(-dev)?$"; then
            log_error "$file: version '$version' must be in X.Y.Z or X.Y.Z-dev format"
            return 1
        fi
    fi

    return 0
}

# Validate marketplace.json
validate_marketplace_json() {
    local file=$1

    # Check JSON syntax
    if ! jq empty "$file" 2>/dev/null; then
        log_error "$file: Invalid JSON syntax"
        return 1
    fi

    # Check required fields
    if ! jq -e '.name' "$file" > /dev/null 2>&1; then
        log_error "$file: Missing 'name' field"
        return 1
    fi

    if ! jq -e '.plugins' "$file" > /dev/null 2>&1; then
        log_error "$file: Missing 'plugins' array"
        return 1
    fi

    # Validate plugins is an array
    if ! jq -e '.plugins | type == "array"' "$file" > /dev/null 2>&1; then
        log_error "$file: 'plugins' must be an array"
        return 1
    fi

    return 0
}

# Main validation
echo "=========================================="
echo "Agent Teams Repository Validation"
echo "=========================================="
echo ""

# Validate skills (supports nested directories: skills/*/SKILL.md and skills/*/*/SKILL.md)
echo "Validating Skills..."
skill_count=0
while IFS= read -r skill_file; do
    [ -z "$skill_file" ] && continue
    log_info "Checking $skill_file"
    validate_frontmatter "$skill_file" && log_success "Frontmatter valid"
    validate_description "$skill_file"
    validate_skill_size "$skill_file"
    ((skill_count++)) || true
done < <(find . -type f -name "SKILL.md" \( -path "./skills/*" -o -path "./plugins/*/skills/*" \) 2>/dev/null)
if [ $skill_count -eq 0 ]; then
    log_info "No skills found"
fi
echo ""

# Validate agents (agents/*/*.md - each agent in its own subdirectory)
echo "Validating Agents..."
agent_count=0
while IFS= read -r agent_file; do
    [ -z "$agent_file" ] && continue
    log_info "Checking $agent_file"
    validate_frontmatter "$agent_file" && log_success "Frontmatter valid"
    validate_description "$agent_file"
    validate_agent_fields "$agent_file"
    ((agent_count++)) || true
done < <(find . -type f -name "*.md" \( -path "./agents/*" -o -path "./plugins/*/agents/*" \) 2>/dev/null)
if [ $agent_count -eq 0 ]; then
    log_info "No agents found"
fi
echo ""

# Validate commands (commands/*.md - all frontmatter fields are optional per official docs)
echo "Validating Commands..."
cmd_count=0
while IFS= read -r cmd_file; do
    [ -z "$cmd_file" ] && continue
    log_info "Checking $cmd_file"
    local_content=$(cat "$cmd_file")

    # Check if frontmatter exists (optional but validate if present)
    if echo "$local_content" | head -1 | grep -q "^---$"; then
        cmd_frontmatter=$(echo "$local_content" | sed -n '/^---$/,/^---$/p' | sed '1d;$d')

        # Validate model field if present (can now be any valid proxy model string)
        if echo "$cmd_frontmatter" | grep -q "^model:"; then
            cmd_model=$(echo "$cmd_frontmatter" | grep "^model:" | sed 's/^model:[[:space:]]*//')
            if ! echo "$cmd_model" | grep -qE "^[a-zA-Z0-9_\.\/-]+$"; then
                log_error "$cmd_file: Invalid model '$cmd_model' (must be alphanumeric with hyphens, underscores, dots, or slashes)"
            fi
        fi

        # Validate description length and allowed-tools format
        validate_command_frontmatter "$cmd_file" "$cmd_frontmatter"

        log_success "Frontmatter valid"
    else
        log_success "No frontmatter (valid - all fields optional)"
    fi
    ((cmd_count++)) || true
done < <(find . -type f -name "*.md" \( -path "./commands/*" -o -path "./plugins/*/commands/*" \) 2>/dev/null)
if [ $cmd_count -eq 0 ]; then
    log_info "No commands found"
fi
echo ""

# Validate hooks
echo "Validating Hooks..."
hooks_found=0
for hooks_dir in hooks plugins/*/hooks; do
    [ -d "$hooks_dir" ] || continue

    if [ -f "$hooks_dir/hooks.json" ]; then
        hooks_found=1
        log_info "Checking $hooks_dir/hooks.json"
        if jq empty "$hooks_dir/hooks.json" 2>/dev/null; then
            log_success "hooks.json valid JSON"
            validate_hooks_schema "$hooks_dir/hooks.json" && log_success "hooks.json schema valid"
        else
            log_error "$hooks_dir/hooks.json: Invalid JSON syntax"
        fi

        # Check shell scripts are executable
        for hook_script in "$hooks_dir"/*.sh; do
            if [ -f "$hook_script" ]; then
                log_info "Checking $hook_script"
                if [ -x "$hook_script" ]; then
                    log_success "$hook_script is executable"
                else
                    log_error "$hook_script is not executable (run: chmod +x $hook_script)"
                fi
            fi
        done

        # Run hook integration tests if available
        if [ -f "$hooks_dir/tests/test-hooks.sh" ]; then
            log_info "Running hook integration tests..."
            if [ -x "$hooks_dir/tests/test-hooks.sh" ]; then
                if "$hooks_dir/tests/test-hooks.sh" > /tmp/hook-tests-output.txt 2>&1; then
                    log_success "Hook integration tests passed"
                else
                    log_error "Hook integration tests failed"
                    cat /tmp/hook-tests-output.txt
                fi
            else
                log_error "$hooks_dir/tests/test-hooks.sh is not executable"
            fi
        fi
    fi
done
if [ $hooks_found -eq 0 ]; then
    log_info "No hooks/hooks.json found"
fi
echo ""

# Validate feature metadata
echo "Validating Feature Metadata..."
feature_count=0
while IFS= read -r meta_file; do
    [ -z "$meta_file" ] && continue
    log_info "Checking $meta_file"

    # Validate .meta.json structure and fields
    validation_output=$(python3 -c "
import json
import sys

always_required = ['id', 'status', 'created']
deprecated = ['worktree', 'currentPhase']

try:
    with open('$meta_file') as f:
        meta = json.load(f)
except json.JSONDecodeError as e:
    print(f'ERROR: Invalid JSON: {e}')
    sys.exit(1)

errors = []
warnings = []
status = meta.get('status')

# Check always-required fields
for field in always_required:
    if field not in meta:
        errors.append(f'Missing required field: {field}')

# Status-aware required fields
if status != 'planned':
    for field in ['mode', 'branch']:
        if field not in meta or meta[field] is None:
            errors.append(f\"Missing required field: {field} (required when status != 'planned')\")
else:
    # Planned features: mode and branch should be null
    if meta.get('mode') is not None:
        warnings.append(\"Field 'mode' should be null when status is 'planned'\")
    if meta.get('branch') is not None:
        warnings.append(\"Field 'branch' should be null when status is 'planned'\")
    if meta.get('completed') is not None:
        errors.append(\"Field 'completed' must be null when status is 'planned'\")

# Check slug/name (slug is required, name is deprecated)
if 'slug' not in meta:
    if 'name' in meta:
        errors.append(\"Field 'name' must be renamed to 'slug'\")
    else:
        errors.append('Missing required field: slug')

# Check deprecated fields
for field in deprecated:
    if field in meta:
        warnings.append(f\"Deprecated field '{field}' should be removed\")

# Status consistency checks
completed = meta.get('completed')

if status == 'active' and completed is not None:
    errors.append(\"Status is 'active' but 'completed' is set\")

if status in ['completed', 'abandoned'] and completed is None:
    errors.append(f\"Status is '{status}' but 'completed' is not set\")

for e in errors:
    print(f'ERROR: {e}')
for w in warnings:
    print(f'WARNING: {w}')

sys.exit(1 if errors else 0)
" 2>&1) && python_exit=0 || python_exit=$?
    if [ $python_exit -eq 0 ]; then
        if [ -n "$validation_output" ]; then
            # Has warnings but no errors - use here-string to avoid subshell
            while IFS= read -r line; do
                [[ "$line" == WARNING:* ]] && log_warning "${line#WARNING: }"
            done <<< "$validation_output"
            log_success ".meta.json valid (with warnings)"
        else
            log_success ".meta.json valid"
        fi
    else
        # Use here-string to avoid subshell variable scope issue
        while IFS= read -r line; do
            [[ "$line" == ERROR:* ]] && log_error "$meta_file: ${line#ERROR: }"
            [[ "$line" == WARNING:* ]] && log_warning "${line#WARNING: }"
        done <<< "$validation_output"
    fi
    ((feature_count++)) || true
done < <(find docs/features -name ".meta.json" -type f 2>/dev/null)
if [ $feature_count -eq 0 ]; then
    log_info "No feature metadata found"
fi
echo ""

# Validate plugin.json files
echo "Validating Plugin Manifests..."
while IFS= read -r plugin_json; do
    [ -z "$plugin_json" ] && continue
    log_info "Checking $plugin_json"
    validate_plugin_json "$plugin_json" && log_success "plugin.json valid"
    # Check that .claude-plugin/ only contains allowed files
    validate_plugin_dir_structure "$(dirname "$plugin_json")"
done < <(find . -path "*/.claude-plugin/plugin.json" -type f 2>/dev/null)
echo ""

# Validate marketplace.json
echo "Validating Marketplace..."
while IFS= read -r marketplace_json; do
    [ -z "$marketplace_json" ] && continue
    log_info "Checking $marketplace_json"
    validate_marketplace_json "$marketplace_json" && log_success "marketplace.json valid"
done < <(find . -path "*/.claude-plugin/marketplace.json" -type f 2>/dev/null)
echo ""

# Check for stale project-level .mcp.json
echo "Checking MCP Configuration..."
if [ -f ".mcp.json" ]; then
    log_warning ".mcp.json exists at project root — MCP servers should be declared in plugin.json mcpServers instead"
fi

# Validate mcpServers script references in plugin.json files
while IFS= read -r plugin_json; do
    [ -z "$plugin_json" ] && continue
    local_plugin_dir=$(dirname "$(dirname "$plugin_json")")
    if jq -e '.mcpServers' "$plugin_json" > /dev/null 2>&1; then
        for server_name in $(jq -r '.mcpServers | keys[]' "$plugin_json" 2>/dev/null); do
            local_cmd=$(jq -r ".mcpServers[\"$server_name\"].command" "$plugin_json")
            # Replace ${CLAUDE_PLUGIN_ROOT} with the plugin's directory
            local_resolved="${local_cmd//\$\{CLAUDE_PLUGIN_ROOT\}/$local_plugin_dir}"
            if [ ! -f "$local_resolved" ]; then
                log_error "$plugin_json: mcpServers.$server_name command not found: $local_resolved"
            elif [ ! -x "$local_resolved" ]; then
                log_error "$plugin_json: mcpServers.$server_name command not executable: $local_resolved"
            else
                log_success "mcpServers.$server_name: $local_resolved exists and is executable"
            fi
        done
    fi
done < <(find . -path "*/.claude-plugin/plugin.json" -type f 2>/dev/null)
echo ""

# Validate no hardcoded plugin paths in component markdown files
echo "Checking Path Portability..."
hardcoded_path_errors=0
while IFS= read -r md_file; do
    [ -z "$md_file" ] && continue
    # Skip dev-only files, READMEs, and plans
    case "$md_file" in
        */sync-cache.md|*/README*.md|*/plan*.md) continue ;;
    esac
    # Search for hardcoded plugins/pd/ paths with 1-line context
    # Skip lines (or preceding context lines) with fallback/conditional markers
    prev_line=""
    while IFS= read -r match_line; do
        [ -z "$match_line" ] && continue
        if [ "$match_line" = "--" ]; then
            prev_line=""
            continue
        fi
        if echo "$match_line" | grep -q 'plugins/pd/' 2>/dev/null; then
            is_fallback=0
            for check_line in "$match_line" "$prev_line"; do
                case "$check_line" in
                    *[Ff]allback*|*"dev workspace"*|*"If "*exists*|*"if "*exists*) is_fallback=1 ;;
                esac
            done
            if [ $is_fallback -eq 0 ]; then
                log_error "$md_file: Hardcoded plugin path: $(echo "$match_line" | sed 's/^[[:space:]]*//' | head -c 120)"
                ((hardcoded_path_errors++)) || true
            fi
        fi
        prev_line="$match_line"
    done < <(grep -B1 'plugins/pd/' "$md_file" 2>/dev/null || true)
done < <(find ./plugins/pd/agents ./plugins/pd/skills ./plugins/pd/commands -name "*.md" -type f 2>/dev/null)
if [ $hardcoded_path_errors -eq 0 ]; then
    log_success "No hardcoded plugin paths in component files"
else
    log_error "Found $hardcoded_path_errors hardcoded plugin path(s) — use two-location Glob or base directory derivation instead"
fi

# Check for hardcoded artifact paths in component files
echo "Checking Artifact Path Portability..."
artifact_path_errors=0
# Patterns that should use {pd_artifacts_root} instead of hardcoded docs/
artifact_patterns='docs/features/\|docs/brainstorms/\|docs/projects/\|docs/knowledge-bank/\|docs/backlog\|docs/rca/'
while IFS= read -r md_file; do
    [ -z "$md_file" ] && continue
    while IFS= read -r match_line; do
        [ -z "$match_line" ] && continue
        # Skip lines that already use the config variable or are in Config Variables section
        if echo "$match_line" | grep -q 'pd_artifacts_root\|Config Variables'; then
            continue
        fi
        log_error "$md_file: Hardcoded artifact path: $(echo "$match_line" | sed 's/^[[:space:]]*//' | head -c 120)"
        ((artifact_path_errors++)) || true
    done < <(grep -n "$artifact_patterns" "$md_file" 2>/dev/null || true)
done < <(find ./plugins/pd/skills -name "SKILL.md" -type f 2>/dev/null; find ./plugins/pd/commands -name "*.md" -type f 2>/dev/null; find ./plugins/pd/agents -name "*.md" -type f 2>/dev/null)
if [ $artifact_path_errors -eq 0 ]; then
    log_success "No hardcoded artifact paths in component files"
else
    log_error "Found $artifact_path_errors hardcoded artifact path(s) — use {pd_artifacts_root} instead"
fi

# Check for hardcoded branch targets in component files
branch_target_errors=0
branch_patterns='checkout develop\|pull.*origin.*develop\|merge.*develop\|develop\.\.HEAD\|develop\.\.\.'
while IFS= read -r md_file; do
    [ -z "$md_file" ] && continue
    while IFS= read -r match_line; do
        [ -z "$match_line" ] && continue
        if echo "$match_line" | grep -q 'pd_base_branch\|Config Variables'; then
            continue
        fi
        log_error "$md_file: Hardcoded branch target: $(echo "$match_line" | sed 's/^[[:space:]]*//' | head -c 120)"
        ((branch_target_errors++)) || true
    done < <(grep -n "$branch_patterns" "$md_file" 2>/dev/null || true)
done < <(find ./plugins/pd/skills -name "SKILL.md" -type f 2>/dev/null; find ./plugins/pd/commands -name "*.md" -type f 2>/dev/null)
if [ $branch_target_errors -eq 0 ]; then
    log_success "No hardcoded branch targets in component files"
else
    log_error "Found $branch_target_errors hardcoded branch target(s) — use {pd_base_branch} instead"
fi
echo ""

# Check for @plugins/ includes in command files
at_include_errors=0
while IFS= read -r cmd_file; do
    [ -z "$cmd_file" ] && continue
    while IFS= read -r match_line; do
        [ -z "$match_line" ] && continue
        log_error "$cmd_file: @include with hardcoded path: $(echo "$match_line" | sed 's/^[[:space:]]*//' | head -c 120)"
        ((at_include_errors++)) || true
    done < <(grep -n '@plugins/' "$cmd_file" 2>/dev/null || true)
done < <(find ./plugins/pd/commands -name "*.md" -type f 2>/dev/null)
if [ $at_include_errors -eq 0 ]; then
    log_success "No @plugins/ includes in command files"
else
    log_error "Found $at_include_errors @plugins/ include(s) — replace with inline Read via two-location Glob"
fi
echo ""

# Validate hook ERR trap usage
echo "Checking Hook ERR Traps..."
err_trap_missing=0
for hook_script in plugins/pd/hooks/*.sh; do
    [ -f "$hook_script" ] || continue
    basename=$(basename "$hook_script")
    # Skip non-hook scripts that don't source common.sh
    case "$basename" in
        cleanup-locks.sh|cleanup-sandbox.sh) continue ;;
    esac
    # Check if it sources common.sh and has install_err_trap
    if grep -q 'source.*common\.sh' "$hook_script" 2>/dev/null; then
        if ! grep -q 'install_err_trap' "$hook_script" 2>/dev/null; then
            log_error "$hook_script: Sources common.sh but missing install_err_trap call"
            ((err_trap_missing++)) || true
        fi
    fi
done
if [ $err_trap_missing -eq 0 ]; then
    log_success "All hooks with common.sh have install_err_trap"
fi
echo ""

# Validate entry-point mkdir guards
echo "Checking Entry-Point mkdir Guards..."
mkdir_missing=0
mkdir_checks=(
    "plugins/pd/skills/brainstorming/SKILL.md:mkdir"
    "plugins/pd/commands/create-feature.md:mkdir"
    "plugins/pd/commands/add-to-backlog.md:mkdir"
    "plugins/pd/skills/root-cause-analysis/SKILL.md:mkdir"
    "plugins/pd/skills/retrospecting/SKILL.md:mkdir"
)
for check in "${mkdir_checks[@]}"; do
    file="${check%%:*}"
    pattern="${check##*:}"
    if [ -f "$file" ]; then
        if ! grep -q "$pattern" "$file" 2>/dev/null; then
            log_error "$file: Missing $pattern guard for directory creation"
            ((mkdir_missing++)) || true
        fi
    fi
done
if [ $mkdir_missing -eq 0 ]; then
    log_success "All entry-point files have mkdir guards"
fi
echo ""


# Check for subjective adjectives in plugin component files (content-level check)
# Skips */references/* (domain-specific reference material)
# Subtracts known domain-specific compound matches
echo "Checking for Subjective Adjectives..."
ADJECTIVE_VIOLATIONS=0
ADJECTIVE_PATTERN='\b(appropriate|sufficient|robust|thorough|proper|adequate|reasonable)\b'
# Domain-specific compound exceptions (not violations)
ADJECTIVE_EXCEPTIONS='(sufficient sample|appropriate statistical test|sufficient data|robust standard error)'
ADJECTIVE_FILES=$(grep -rli --include="*.md" -E "$ADJECTIVE_PATTERN" plugins/pd/agents plugins/pd/skills plugins/pd/commands 2>/dev/null | grep -v '/references/' || true)
if [ -n "$ADJECTIVE_FILES" ]; then
    while IFS= read -r file; do
        count=$(grep -ciE "$ADJECTIVE_PATTERN" "$file" 2>/dev/null || true)
        exceptions=$(grep -ciE "$ADJECTIVE_EXCEPTIONS" "$file" 2>/dev/null || true)
        net=$((count - exceptions))
        if [ "$net" -gt 0 ]; then
            log_error "$file: $net subjective adjective(s) found — replace with measurable criteria"
            ((ADJECTIVE_VIOLATIONS += net)) || true
        fi
    done <<< "$ADJECTIVE_FILES"
fi
if [ $ADJECTIVE_VIOLATIONS -eq 0 ]; then
    log_success "No subjective adjectives found in component files"
fi
echo ""

# Validate setup script exists
echo "Checking Setup Scripts..."
for script in plugins/pd/scripts/doctor.sh plugins/pd/scripts/setup.sh; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            log_success "$script exists and is executable"
        else
            log_error "$script exists but is not executable"
        fi
    else
        log_warning "$script not found"
    fi
done
echo ""

# Validate pattern_promotion Python package (pytest + importability)
echo "Checking pattern_promotion Python Package..."
PP_DIR="plugins/pd/hooks/lib/pattern_promotion"
PP_PY="plugins/pd/.venv/bin/python"
if [ -d "$PP_DIR" ]; then
    if [ -x "$PP_PY" ]; then
        # Import health check (fast, no test discovery cost)
        if PYTHONPATH="plugins/pd/hooks/lib" "$PP_PY" -c "import pattern_promotion; import pattern_promotion.kb_parser; import pattern_promotion.classifier; import pattern_promotion.apply; import pattern_promotion.generators.hook; import pattern_promotion.generators.skill; import pattern_promotion.generators.agent; import pattern_promotion.generators.command" 2>/dev/null; then
            log_success "pattern_promotion package imports cleanly"
        else
            log_error "pattern_promotion package fails to import"
        fi

        # Full pytest run (deterministic, <5s)
        if PYTHONPATH="plugins/pd/hooks/lib" "$PP_PY" -m pytest "$PP_DIR" -q --tb=line > /tmp/pp-tests-output.txt 2>&1; then
            log_success "pattern_promotion pytest suite passed ($(grep -oE '[0-9]+ passed' /tmp/pp-tests-output.txt | head -1))"
        else
            log_error "pattern_promotion pytest suite failed"
            tail -20 /tmp/pp-tests-output.txt
        fi
    else
        log_warning "$PP_PY not found — skipping pattern_promotion checks (run plugins/pd/scripts/setup.sh)"
    fi
else
    log_info "pattern_promotion package not found — skipping"
fi
echo ""

# --- Hooks.json Registration Contract (feature 104 FR-1 + FR-2) ---
# Asserts hooks.json keeps the registration shape feature 102 / 104 depend on.
# Defends against silent hook-misconfiguration regressions.
echo "Checking Hooks.json Registration Contract..."
if jq -e '.hooks.UserPromptSubmit | length == 1' plugins/pd/hooks/hooks.json > /dev/null 2>&1; then
    log_success "hooks.json: UserPromptSubmit registered (1 entry)"
else
    log_error "hooks.json: UserPromptSubmit length != 1"
fi
if jq -e '.hooks.Stop | length == 2' plugins/pd/hooks/hooks.json > /dev/null 2>&1; then
    log_success "hooks.json: Stop array has 2 entries"
else
    log_error "hooks.json: Stop length != 2"
fi
if jq -e '.hooks.Stop[1].hooks[0] | (.async == true and .timeout == 30)' plugins/pd/hooks/hooks.json > /dev/null 2>&1; then
    log_success "hooks.json: Stop[1] has async:true, timeout:30"
else
    log_error "hooks.json: Stop[1] async/timeout assertion failed"
fi
if grep -qE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md; then
    log_success "retrospecting/SKILL.md references extract_workarounds"
else
    log_error "retrospecting/SKILL.md missing extract_workarounds reference"
fi
echo ""

# --- Codex Reviewer Routing exclusion guard (feature 103) ---
# Files that reference codex-routing.md AND dispatch pd:security-reviewer MUST
# include explicit exclusion language. Defends against future regression where
# codex routing accidentally captures security-reviewer.
echo "Checking Codex Reviewer Routing exclusion..."
codex_routing_exclusion_violations=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    # Skip the reference doc itself.
    [[ "$f" == "plugins/pd/references/codex-routing.md" ]] && continue
    # Files that mention codex-routing must either (a) explicitly exclude
    # security-reviewer when they dispatch it, or (b) explicitly note that
    # security-reviewer is not dispatched at this phase.
    if grep -q "subagent_type:.*pd:security-reviewer" "$f" 2>/dev/null; then
        # Dispatches security-reviewer → MUST contain exclusion language.
        if ! grep -qE "always.*Task.*pd:security-reviewer|NOT.*pd:security-reviewer|security.*always.*Anthropic|security-reviewer.*always.*standard" "$f"; then
            log_error "$f: references codex-routing.md AND dispatches pd:security-reviewer but lacks explicit exclusion language"
            codex_routing_exclusion_violations=$((codex_routing_exclusion_violations + 1))
        fi
    else
        # Does not dispatch security-reviewer → MUST contain "no security review at this phase" indicator.
        if ! grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" "$f"; then
            log_error "$f: references codex-routing.md but lacks 'no security review at this phase' indicator"
            codex_routing_exclusion_violations=$((codex_routing_exclusion_violations + 1))
        fi
    fi
done < <(grep -rl "plugins/pd/references/codex-routing.md\|codex-routing\.md" plugins/pd/commands plugins/pd/skills 2>/dev/null)

# FR-2b (feature 105): allowlist+count assertion for codex-routing references.
# Catches drift where a preamble is removed from one of the 11 expected sites,
# or a 12th non-target file accidentally references codex-routing.md.
codex_routing_allowlist_violations=0
if [[ -f "./validate.sh" && -d "./plugins/pd" ]]; then
    expected_codex_files="plugins/pd/commands/specify.md
plugins/pd/commands/design.md
plugins/pd/commands/create-plan.md
plugins/pd/commands/implement.md
plugins/pd/commands/finish-feature.md
plugins/pd/skills/brainstorming/SKILL.md
plugins/pd/commands/secretary.md
plugins/pd/commands/taskify.md
plugins/pd/commands/review-ds-code.md
plugins/pd/commands/review-ds-analysis.md
plugins/pd/skills/decomposing/SKILL.md"
    # Note: alternation is intentionally redundant (mirrors validate.sh main-loop grep verbatim).
    # Scope (commands+skills, NOT references) excludes codex-routing.md itself from the discovery set.
    actual_codex_files=$(grep -rl "plugins/pd/references/codex-routing.md\|codex-routing\.md" plugins/pd/commands plugins/pd/skills 2>/dev/null | sort)
    expected_sorted=$(echo "$expected_codex_files" | sort)
    if [ "$actual_codex_files" != "$expected_sorted" ]; then
        log_error "Codex routing coverage drift: actual file set differs from allowlist (feature 105 FR-2b)"
        diff <(echo "$expected_sorted") <(echo "$actual_codex_files") | head -20 | while IFS= read -r line; do log_error "  $line"; done || true
        codex_routing_allowlist_violations=$((codex_routing_allowlist_violations + 1))
    fi
else
    log_error "FR-2b allowlist check requires repo-root cwd (validate.sh and plugins/pd not found in cwd)"
    codex_routing_allowlist_violations=$((codex_routing_allowlist_violations + 1))
fi
[ "$codex_routing_exclusion_violations" = "0" ] && log_info "Codex Reviewer Routing exclusions validated"

[ "$codex_routing_allowlist_violations" = "0" ] && log_info "Codex routing coverage allowlist validated (11 expected files)"
echo ""

# --- docs-sync regression guards (feature 085 FR-8; from feature 080 AC-7/AC-11) ---
# (a) The literal `threshold=0.70` must NOT resurface in non-test .py files
#     under plugins/pd/ — feature 080 established 0.55 as the correct default.
#     `--exclude='test_*.py'` is the right filter because pd's inline-test
#     convention places test files next to sources (not in tests/ subdirs).
bad_threshold=$(grep -rE --include='*.py' --exclude='test_*.py' 'threshold=0\.70' plugins/pd/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$bad_threshold" != "0" ]; then
    echo -e "${RED}FAIL: threshold=0.70 literal resurfaced ($bad_threshold occurrences)${NC}"
    exit 1
fi
# (b) README_FOR_DEV.md must continue documenting the memory_influence_*
#     config knobs (feature 080 committed to at least 3 distinct references).
influence_refs=$(grep -c 'memory_influence_' README_FOR_DEV.md 2>/dev/null || echo 0)
if [ "$influence_refs" -lt 3 ]; then
    echo -e "${RED}FAIL: memory_influence_* docs in README_FOR_DEV.md dropped below 3 ($influence_refs)${NC}"
    exit 1
fi

# --- circular-import smoke test (feature 085 FR-8 / SC-7) ---
# `config_utils.py` must stay importable without pulling `ranking`,
# `database`, or any other semantic_memory submodule. A regression
# that adds such an import will surface as ImportError here.
if ! PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils; from semantic_memory import ranking' 2>/dev/null; then
    echo -e "${RED}FAIL: circular import detected in semantic_memory.config_utils${NC}"
    exit 1
fi

# --- hook JSON schema: hookSpecificOutput must include hookEventName (feature 087 RCA) ---
# Per CC schema: every hook EMITTING `hookSpecificOutput` MUST include
# `hookEventName` inside the same block. Missing the field causes
# "Hook JSON output validation failed" errors in user sessions.
#
# Detect emitters (not consumers) via the JSON-emission signature:
# `"hookSpecificOutput":` — the literal double-quoted key followed by a
# colon. This matches emitted JSON objects; it does NOT match Python
# code accessing the field via `d['hookSpecificOutput']` or `d.get(...)`.
# Skip the tests/ directory (test scripts consume hook output, not emit).
# Skip lib/ — the helper itself and its self-test legitimately reference
# the field in constructors + assertions.
bad_hook_schema=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    case "$f" in
        plugins/pd/hooks/tests/*) continue ;;
        plugins/pd/hooks/lib/*) continue ;;
    esac
    # Emitter check: file must also reference hookEventName so the
    # emitted block is schema-compliant.
    if ! grep -qE '"hookEventName"' "$f" 2>/dev/null; then
        echo -e "${RED}FAIL: hookSpecificOutput in $f missing hookEventName${NC}"
        bad_hook_schema=$((bad_hook_schema + 1))
    fi
done < <(grep -rlE '"hookSpecificOutput"[[:space:]]*:' plugins/pd/hooks/ 2>/dev/null || true)
if [ "$bad_hook_schema" -gt 0 ]; then
    echo -e "${RED}Hook schema validation failed: $bad_hook_schema file(s) missing hookEventName${NC}"
    echo -e "${RED}  → Prefer the shared helper: source lib/common.sh; emit_hook_json <event> <payload>${NC}"
    exit 1
fi
echo ""

# Summary
echo "=========================================="
echo "Validation Complete"
echo "=========================================="
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}Validation failed with $ERRORS error(s)${NC}"
    exit 1
else
    echo -e "${GREEN}Validation passed${NC}"
    exit 0
fi
