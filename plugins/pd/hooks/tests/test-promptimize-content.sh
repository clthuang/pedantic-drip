#!/usr/bin/env bash
# Content regression tests for the prompt-intelligence-system feature
# Run: bash plugins/pd/hooks/tests/test-promptimize-content.sh
#
# These tests verify critical content in the promptimize skill, scoring rubric,
# prompt guidelines, and related commands. They prevent accidental deletion of
# key sections, structural elements, and behavioral contracts during edits.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${HOOKS_DIR}" && while [[ ! -d .git ]] && [[ $PWD != / ]]; do cd ..; done && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_test() {
    echo -e "TEST: $1"
    ((TESTS_RUN++)) || true
}

log_pass() {
    echo -e "${GREEN}  PASS${NC}"
    ((TESTS_PASSED++)) || true
}

log_fail() {
    echo -e "${RED}  FAIL: $1${NC}"
    ((TESTS_FAILED++)) || true
}



# --- Paths ---
PLUGIN_DIR="${PROJECT_ROOT}/plugins/pd"
SKILL_DIR="${PLUGIN_DIR}/skills/promptimize"
SKILL_FILE="${SKILL_DIR}/SKILL.md"
RUBRIC_FILE="${SKILL_DIR}/references/scoring-rubric.md"
GUIDELINES_FILE="${SKILL_DIR}/references/prompt-guidelines.md"
PROMPTIMIZE_CMD="${PLUGIN_DIR}/commands/promptimize.md"
REFRESH_CMD="${PLUGIN_DIR}/commands/refresh-prompt-guidelines.md"


# ============================================================
# Dimension 1: BDD Scenarios (spec-driven content assertions)
# ============================================================

# --- scoring-rubric.md ---

# derived_from: spec:AC-rubric-dimensions (scoring rubric documents exactly 10 dimensions)
test_rubric_has_exactly_10_dimensions() {
    log_test "scoring-rubric.md documents exactly 10 scoring dimensions"

    # Given the scoring rubric file exists
    if [[ ! -f "$RUBRIC_FILE" ]]; then
        log_fail "File not found: $RUBRIC_FILE"
        return
    fi
    # When we count rows in the Behavioral Anchors table (which have descriptive text, NOT "Evaluated"/"Auto-pass")
    local dim_count
    dim_count=$(sed -n '/^## Behavioral Anchors/,/^## /p' "$RUBRIC_FILE" | grep -cE '^\| (Structure|Token|Description|Persuasion|Technique|Prohibition|Example|Progressive|Context|Cache)')
    # Then there are exactly 10 dimensions
    if [[ "$dim_count" -eq 10 ]]; then
        log_pass
    else
        log_fail "Expected 10 dimensions, found $dim_count"
    fi
}

# derived_from: spec:AC-rubric-scoring (each dimension has pass/partial/fail anchors)
test_rubric_has_pass_partial_fail_columns() {
    log_test "scoring-rubric.md has Pass/Partial/Fail columns in behavioral anchors"

    # Given the rubric file
    if [[ ! -f "$RUBRIC_FILE" ]]; then
        log_fail "File not found: $RUBRIC_FILE"
        return
    fi
    # When we check the table header
    local header
    header=$(grep -E '^\| Dimension' "$RUBRIC_FILE" | head -1)
    # Then it contains Pass (3), Partial (2), and Fail (1) headers
    if [[ "$header" == *"Pass (3)"* ]] && [[ "$header" == *"Partial (2)"* ]] && [[ "$header" == *"Fail (1)"* ]]; then
        log_pass
    else
        log_fail "Missing Pass/Partial/Fail columns in header: $header"
    fi
}

# derived_from: spec:AC-rubric-applicability (Component Type Applicability table present)
test_rubric_has_component_type_applicability_table() {
    log_test "scoring-rubric.md has Component Type Applicability table"

    # Given the rubric file
    if [[ ! -f "$RUBRIC_FILE" ]]; then
        log_fail "File not found: $RUBRIC_FILE"
        return
    fi
    # When we search for the section heading
    # Then it exists
    if grep -q '## Component Type Applicability' "$RUBRIC_FILE"; then
        log_pass
    else
        log_fail "Missing '## Component Type Applicability' section"
    fi
}

# derived_from: spec:AC-rubric-autopass (auto-pass entries exist for correct component types)
test_rubric_has_auto_pass_entries() {
    log_test "scoring-rubric.md has Auto-pass entries in applicability table"

    # Given the rubric file
    if [[ ! -f "$RUBRIC_FILE" ]]; then
        log_fail "File not found: $RUBRIC_FILE"
        return
    fi
    # When we count Auto-pass occurrences in the table
    local ap_count
    ap_count=$(grep -c 'Auto-pass' "$RUBRIC_FILE")
    # Then there are at least 1 (the spec specifies several: Persuasion/Command, etc.)
    if [[ "$ap_count" -ge 1 ]]; then
        log_pass
    else
        log_fail "Expected at least 1 Auto-pass entry, found $ap_count"
    fi
}

# derived_from: spec:AC-rubric-applicability-columns (table has Skill, Agent, Command columns)
test_rubric_applicability_has_three_component_columns() {
    log_test "scoring-rubric.md applicability table has Skill/Agent/Command columns"

    if [[ ! -f "$RUBRIC_FILE" ]]; then
        log_fail "File not found: $RUBRIC_FILE"
        return
    fi
    local header
    header=$(grep -E '^\| Dimension.*Skill' "$RUBRIC_FILE" | head -1)
    if [[ "$header" == *"Skill"* ]] && [[ "$header" == *"Agent"* ]] && [[ "$header" == *"Command"* ]]; then
        log_pass
    else
        log_fail "Missing Skill/Agent/Command columns: $header"
    fi
}

# --- prompt-guidelines.md ---

# derived_from: spec:AC-guidelines-date (has "Last Updated" date field)
test_guidelines_has_last_updated_date() {
    log_test "prompt-guidelines.md has 'Last Updated' date heading"

    if [[ ! -f "$GUIDELINES_FILE" ]]; then
        log_fail "File not found: $GUIDELINES_FILE"
        return
    fi
    # When we search for the date heading pattern
    if grep -qE '^## Last Updated: [0-9]{4}-[0-9]{2}-[0-9]{2}' "$GUIDELINES_FILE"; then
        log_pass
    else
        log_fail "Missing '## Last Updated: YYYY-MM-DD' heading"
    fi
}

# derived_from: spec:AC-guidelines-count (at least 15 guidelines with citations)
test_guidelines_has_at_least_15_guidelines() {
    log_test "prompt-guidelines.md has at least 15 guidelines with citations"

    if [[ ! -f "$GUIDELINES_FILE" ]]; then
        log_fail "File not found: $GUIDELINES_FILE"
        return
    fi
    # When we count lines that look like guidelines (numbered items or bold-prefixed bullets with citations)
    local count
    count=$(grep -cE '(\*\*.*\*\*.*\[|^[0-9]+\. \*\*.*\[)' "$GUIDELINES_FILE")
    # Then there are at least 15
    if [[ "$count" -ge 15 ]]; then
        log_pass
    else
        log_fail "Expected >= 15 guidelines with citations, found $count"
    fi
}

# derived_from: spec:AC-guidelines-sections (has all 6 required sections)
test_guidelines_has_core_principles_section() {
    log_test "prompt-guidelines.md has 'Core Principles' section"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Core Principles' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing Core Principles section"; fi
}

test_guidelines_has_plugin_specific_patterns_section() {
    log_test "prompt-guidelines.md has 'Plugin-Specific Patterns' section"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Plugin-Specific Patterns' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing Plugin-Specific Patterns section"; fi
}

test_guidelines_has_persuasion_techniques_section() {
    log_test "prompt-guidelines.md has 'Persuasion Techniques' section"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Persuasion Techniques' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing Persuasion Techniques section"; fi
}

test_guidelines_has_techniques_by_evidence_tier_section() {
    log_test "prompt-guidelines.md has 'Techniques by Evidence Tier' section"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Techniques by Evidence Tier' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing Techniques by Evidence Tier section"; fi
}

test_guidelines_has_anti_patterns_section() {
    log_test "prompt-guidelines.md has 'Anti-Patterns' section"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Anti-Patterns' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing Anti-Patterns section"; fi
}

test_guidelines_has_update_log_section() {
    log_test "prompt-guidelines.md has 'Update Log' section"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Update Log' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing Update Log section"; fi
}

# --- SKILL.md content ---

# derived_from: spec:AC-skill-change-format (uses XML <change> tags, not HTML markers)
test_skill_uses_xml_not_html_markers() {
    log_test "SKILL.md uses XML <change> tags, not HTML CHANGE markers"

    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Assert new XML format present
    if ! grep -q '<change' "$SKILL_FILE"; then log_fail "Missing <change XML tag"; return; fi
    if ! grep -q '</change>' "$SKILL_FILE"; then log_fail "Missing </change> XML tag"; return; fi
    # Assert old HTML format absent
    if grep -q "CHANGE:" "$SKILL_FILE"; then log_fail "Old HTML CHANGE: marker still present"; return; fi
    if grep -q "END CHANGE" "$SKILL_FILE"; then log_fail "Old HTML END CHANGE marker still present"; return; fi
    log_pass
}

# derived_from: spec:AC-cmd-approval (references AskUserQuestion with Accept all/Accept some/Reject in command)
test_cmd_has_all_approval_options() {
    log_test "promptimize.md references all three approval options"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if ! grep -q 'Accept all' "$PROMPTIMIZE_CMD"; then log_fail "Missing 'Accept all' option"; return; fi
    if ! grep -q 'Accept some' "$PROMPTIMIZE_CMD"; then log_fail "Missing 'Accept some' option"; return; fi
    if ! grep -q 'Reject' "$PROMPTIMIZE_CMD"; then log_fail "Missing 'Reject' option"; return; fi
    log_pass
}

# derived_from: spec:AC-skill-components (handles 3 component types)
test_skill_handles_skill_type() {
    log_test "SKILL.md documents skill component type detection"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'SKILL.md' "$SKILL_FILE" && grep -q 'skill' "$SKILL_FILE"; then log_pass; else log_fail "Missing skill type documentation"; fi
}

test_skill_handles_agent_type() {
    log_test "SKILL.md documents agent component type detection"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'agents/' "$SKILL_FILE"; then log_pass; else log_fail "Missing agent type documentation"; fi
}

test_skill_handles_command_type() {
    log_test "SKILL.md documents command component type detection"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'commands/' "$SKILL_FILE"; then log_pass; else log_fail "Missing command type documentation"; fi
}

# derived_from: spec:AC-skill-invalid-path (documents invalid path error with valid patterns)
test_skill_documents_invalid_path_error() {
    log_test "SKILL.md documents invalid path error with expected patterns"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'skills/\*/SKILL.md' "$SKILL_FILE" || grep -q 'skills/<name>/SKILL.md' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing invalid path error message with valid pattern examples"
    fi
}

# derived_from: spec:AC-skill-staleness (documents staleness warning with 30-day threshold)
test_skill_documents_staleness_warning() {
    log_test "SKILL.md documents staleness warning with 30-day threshold"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '30' "$SKILL_FILE" && grep -qi 'stale\|staleness' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing staleness warning with 30-day threshold"
    fi
}

# derived_from: design:skill-phase1 (SKILL.md contains phase1_output tags)
test_skill_has_phase1_output_tags() {
    log_test "SKILL.md contains phase1_output tags"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'phase1_output' "$SKILL_FILE"; then log_pass; else log_fail "Missing phase1_output tags"; fi
}

# derived_from: design:skill-phase2 (SKILL.md contains phase2_output tags)
test_skill_has_phase2_output_tags() {
    log_test "SKILL.md contains phase2_output tags"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'phase2_output' "$SKILL_FILE"; then log_pass; else log_fail "Missing phase2_output tags"; fi
}

# derived_from: design:skill-grading-result (SKILL.md contains grading_result block)
test_skill_has_grading_result_block() {
    log_test "SKILL.md contains grading_result block"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'grading_result' "$SKILL_FILE"; then log_pass; else log_fail "Missing grading_result block"; fi
}

# derived_from: spec:AC1a (phase1 output contains JSON with dimensions array and phase2 contains change tags)
test_skill_phase1_documents_dimensions_array() {
    log_test "SKILL.md phase1_output example contains dimensions array with score/finding/suggestion"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given SKILL.md documents the phase1_output JSON schema
    # When we check for the required JSON fields in the phase1 example
    # Then it includes dimensions, score, finding, and suggestion fields
    if grep -q '"dimensions"' "$SKILL_FILE" && grep -q '"score"' "$SKILL_FILE" && grep -q '"finding"' "$SKILL_FILE" && grep -q '"suggestion"' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Phase1 JSON schema missing dimensions/score/finding/suggestion fields"
    fi
}

# derived_from: spec:AC3 (accept some applies selected dimensions only via multiSelect)
test_cmd_accept_some_uses_multiselect_for_dimension_selection() {
    log_test "promptimize.md Accept some handler uses multiSelect for dimension selection"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Accept some handler in the command
    # When we check for multiSelect in the dimension selection AskUserQuestion
    # Then it uses multiSelect: true for choosing which dimensions to apply
    local multiselect_count
    multiselect_count=$(grep -c '"multiSelect": true' "$PROMPTIMIZE_CMD" || true)
    if [[ "$multiselect_count" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing multiSelect: true in Accept some dimension selection"
    fi
}

# derived_from: spec:AC4 (malformed change tags degrade to accept all / reject only)
test_cmd_malformed_tags_degrade_to_two_option_menu() {
    log_test "promptimize.md documents degradation to Accept all/Reject when tags malformed"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the tag validation failure path in the command
    # When we check for the two-option fallback menu documentation
    # Then it shows Accept all and Reject without Accept some
    if grep -q 'tag_validation_failed' "$PROMPTIMIZE_CMD" && grep -q 'Partial acceptance unavailable' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing degradation documentation for malformed tags"
    fi
}

# derived_from: spec:AC5 (accept all strips all XML change tags producing clean file)
test_cmd_accept_all_strips_change_tags() {
    log_test "promptimize.md Accept all handler strips <change> opening and </change> closing tags"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Accept all handler section
    # When we check for tag stripping documentation
    # Then it documents stripping both opening <change ...> and closing </change> tags
    if grep -q 'Strip.*<change' "$PROMPTIMIZE_CMD" && grep -q '</change>' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing tag stripping in Accept all handler"
    fi
}

# derived_from: spec:AC6 (auto-passed dimensions score 3 and produce no change tags)
test_skill_auto_pass_sets_score_3_and_null_suggestion() {
    log_test "SKILL.md documents auto-pass dimensions: score 3, suggestion null"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the auto-pass documentation in SKILL.md
    # When we check for the auto-pass behavior contract
    # Then it specifies score 3 and suggestion = null
    if grep -q 'Auto-pass' "$SKILL_FILE" && grep -q 'auto_passed' "$SKILL_FILE" && grep -q 'suggestion.*null\|null.*suggestion' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing auto-pass score/suggestion contract"
    fi
}

# derived_from: spec:AC7 (YOLO mode auto-selects Accept all, skips AskUserQuestion)
test_cmd_yolo_auto_selects_accept_all() {
    log_test "promptimize.md YOLO mode auto-selects Accept all and skips AskUserQuestion"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the YOLO mode handling in the command
    # When we check for the auto-select behavior
    # Then it documents auto-selecting Accept all and skipping user interaction
    if grep -q 'YOLO' "$PROMPTIMIZE_CMD" && grep -qi 'auto-select.*Accept all\|Accept all.*auto' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing YOLO auto-select Accept all documentation"
    fi
}

# derived_from: spec:AC8 (staleness warning included in report template)
test_cmd_report_includes_staleness_warning_template() {
    log_test "promptimize.md report template includes staleness warning block"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the report assembly section (Step 7)
    # When we check for the staleness warning template
    # Then it includes a conditional staleness warning with guidelines date
    if grep -q 'staleness_warning' "$PROMPTIMIZE_CMD" && grep -qi 'stale\|guidelines are stale' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing staleness warning in report template"
    fi
}

# derived_from: spec:AC8 (over budget warning for large output in report)
test_cmd_report_includes_over_budget_warning() {
    log_test "promptimize.md report template includes over_budget_warning block"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the report assembly section (Step 7)
    # When we check for the over-budget warning template
    # Then it includes an over_budget_warning conditional
    if grep -q 'over_budget_warning' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing over_budget_warning in report template"
    fi
}

# derived_from: spec:AC10 (drift detection disables accept some option)
test_cmd_drift_detected_disables_accept_some() {
    log_test "promptimize.md drift_detected disables Accept some with explanation"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the drift detection affects the approval menu
    # When we check for drift-based Accept some gating
    # Then it documents that drift_detected disables Accept some
    if grep -q 'drift_detected' "$PROMPTIMIZE_CMD" && grep -qi 'Partial acceptance unavailable.*drift\|drift.*Partial acceptance' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing drift_detected -> Accept some disabled documentation"
    fi
}

# derived_from: spec:R4.5 (all dimensions pass skips approval menu entirely)
test_cmd_score_100_no_changes_skips_approval() {
    log_test "promptimize.md documents skip approval when score 100 and zero ChangeBlocks"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the approval path determination in Step 8a
    # When we check for the all-pass shortcut
    # Then it documents "no improvements needed" and STOP
    if grep -qi 'overall_score.*100\|score.*100' "$PROMPTIMIZE_CMD" && grep -qi 'no improvements needed\|no.*improvements' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing score-100-no-changes skip approval documentation"
    fi
}

# derived_from: spec:R1.1 (phase1 findings: suggestion required when score < 3)
test_skill_suggestion_required_when_score_below_3() {
    log_test "SKILL.md documents suggestion is required when score < 3"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the dimension output schema
    # When we check for the suggestion requirement
    # Then it documents suggestion required for score < 3
    if grep -qi 'suggestion.*required.*score.*<.*3\|required when score.*<.*3\|score < 3.*suggestion' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing suggestion requirement for score < 3"
    fi
}

# derived_from: spec:R5.2 (report strengths exclude auto-passed dimensions)
test_cmd_strengths_section_excludes_auto_passed() {
    log_test "promptimize.md report strengths section excludes auto-passed dimensions"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Strengths section template in Step 7
    # When we check for auto-pass exclusion
    # Then it documents "NOT auto-passed" in the strengths criteria
    if grep -qi 'NOT auto-passed\|not.*auto.pass' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing auto-pass exclusion in Strengths section"
    fi
}

# derived_from: spec:R5.2 (issues table sorts blockers before warnings)
test_cmd_issues_table_blockers_before_warnings() {
    log_test "promptimize.md issues table documents blockers sorted before warnings"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Issues table template in Step 7
    # When we check the sort order documentation
    # Then blockers (fail) appear before warnings (partial)
    if grep -qi 'blocker.*first\|Sort blocker.*then.*warning\|fail.*first.*warning' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing blocker-before-warning sort order documentation"
    fi
}

# derived_from: spec:R4.2 (overlapping dimensions presented as single option in accept some)
test_cmd_overlapping_dimensions_single_option() {
    log_test "promptimize.md documents overlapping (comma-separated) dimensions as single option"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Accept some handler dimension selection
    # When we check for overlapping dimension handling
    # Then it documents comma-separated dimensions as inseparable option
    if grep -qi 'comma-separated\|inseparable\|overlapping' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing overlapping dimensions as single option documentation"
    fi
}

# --- promptimize.md command ---

# derived_from: spec:AC-cmd-delegates (delegates to skill via Skill() call)
test_promptimize_cmd_delegates_to_skill() {
    log_test "promptimize.md delegates to skill via Skill() call"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Skill(' "$PROMPTIMIZE_CMD" && grep -q 'promptimize' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing Skill() delegation to promptimize"
    fi
}

# derived_from: spec:AC-cmd-interactive (asks for component type when no args)
test_promptimize_cmd_asks_component_type() {
    log_test "promptimize.md asks for component type when no arguments"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'AskUserQuestion' "$PROMPTIMIZE_CMD" && grep -q 'component' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing AskUserQuestion for component type selection"
    fi
}

# derived_from: design:cmd-score (promptimize.md contains score computation with round and 30)
test_cmd_has_score_computation() {
    log_test "promptimize.md contains score computation (round and 30)"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'round' "$PROMPTIMIZE_CMD" && grep -q '30' "$PROMPTIMIZE_CMD"; then log_pass; else log_fail "Missing score computation (round and 30)"; fi
}

# derived_from: design:cmd-drift (promptimize.md contains drift_detected)
test_cmd_has_drift_detection() {
    log_test "promptimize.md contains drift_detected"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'drift_detected' "$PROMPTIMIZE_CMD"; then log_pass; else log_fail "Missing drift_detected"; fi
}

# derived_from: design:cmd-tag-validation (promptimize.md contains tag_validation_failed)
test_cmd_has_tag_validation() {
    log_test "promptimize.md contains tag_validation_failed"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'tag_validation_failed' "$PROMPTIMIZE_CMD"; then log_pass; else log_fail "Missing tag_validation_failed"; fi
}

# derived_from: design:cmd-yolo (promptimize.md contains YOLO mode handling)
test_cmd_has_yolo_mode_handling() {
    log_test "promptimize.md contains YOLO mode handling"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'YOLO_MODE\|YOLO' "$PROMPTIMIZE_CMD"; then log_pass; else log_fail "Missing YOLO mode handling"; fi
}

# --- refresh-prompt-guidelines.md command ---

# derived_from: spec:AC-refresh-websearch-fallback (documents WebSearch unavailable fallback)
test_refresh_cmd_documents_websearch_fallback() {
    log_test "refresh-prompt-guidelines.md documents WebSearch unavailable fallback"
    if [[ ! -f "$REFRESH_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'WebSearch.*unavailable\|unavailable.*WebSearch\|WebSearch is unavailable' "$REFRESH_CMD"; then
        log_pass
    else
        log_fail "Missing WebSearch unavailable fallback documentation"
    fi
}

# derived_from: spec:AC-refresh-dedup (documents deduplication against existing)
test_refresh_cmd_documents_deduplication() {
    log_test "refresh-prompt-guidelines.md documents deduplication/diff against existing"
    if [[ ! -f "$REFRESH_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'overlap\|deduplic\|diff.*existing\|compare.*existing\|merge' "$REFRESH_CMD"; then
        log_pass
    else
        log_fail "Missing deduplication documentation"
    fi
}

# derived_from: spec:AC-refresh-changelog (documents changelog update)
test_refresh_cmd_documents_changelog_update() {
    log_test "refresh-prompt-guidelines.md documents changelog/Update Log append"
    if [[ ! -f "$REFRESH_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'Update Log\|changelog\|Changelog' "$REFRESH_CMD"; then
        log_pass
    else
        log_fail "Missing changelog/Update Log documentation"
    fi
}

# derived_from: spec:AC-refresh-preserve-sections (all 6 section names listed in preservation step)
test_refresh_cmd_lists_all_6_sections() {
    log_test "refresh-prompt-guidelines.md lists all 6 section names for preservation"
    if [[ ! -f "$REFRESH_CMD" ]]; then log_fail "File not found"; return; fi
    local missing=0
    for section in "Core Principles" "Plugin-Specific Patterns" "Persuasion Techniques" "Techniques by Evidence Tier" "Anti-Patterns" "Update Log"; do
        if ! grep -q "$section" "$REFRESH_CMD"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 6 expected section names"
    fi
}


# ============================================================
# Dimension 2: Boundary Values
# ============================================================

# derived_from: dimension:boundary (SKILL.md under 500 line budget per CLAUDE.md)
test_skill_under_500_lines() {
    log_test "SKILL.md is under 500 lines (token budget constraint)"

    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    local lines
    lines=$(wc -l < "$SKILL_FILE" | tr -d ' ')
    if [[ "$lines" -le 500 ]]; then
        log_pass
    else
        log_fail "SKILL.md has $lines lines (max 500)"
    fi
}

# derived_from: dimension:boundary (scoring formula: 9*3=27 max, all pass=100)
test_scoring_formula_max_denominator_is_30() {
    log_test "scoring-rubric.md implies denominator of 30 (10 dims * max 3)"

    if [[ ! -f "$RUBRIC_FILE" ]]; then log_fail "File not found"; return; fi
    # Verify exactly 10 dimension rows in behavioral anchors table (section-scoped)
    local dim_count
    dim_count=$(sed -n '/^## Behavioral Anchors/,/^## /p' "$RUBRIC_FILE" | grep -cE '^\| (Structure|Token|Description|Persuasion|Technique|Prohibition|Example|Progressive|Context|Cache)')
    # And verify Pass score is 3
    if [[ "$dim_count" -eq 10 ]] && grep -q 'Pass (3)' "$RUBRIC_FILE"; then
        log_pass
    else
        log_fail "Expected 10 dimensions with Pass(3), found $dim_count dimensions"
    fi
}


# derived_from: dimension:boundary (command validates exactly 10 dimensions in phase1 JSON -- Step 4c)
test_cmd_validates_exactly_10_dimensions_in_phase1() {
    log_test "promptimize.md Step 4c validates dimensions array contains exactly 10 entries"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Phase 1 JSON validation in Step 4c
    # When we check for the 10-entry constraint
    # Then it documents "exactly 10 entries" or "10 entries"
    if grep -q 'exactly 10' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing 'exactly 10' dimension validation in Step 4c"
    fi
}

# derived_from: dimension:boundary (command documents before_context up to 3 lines in ChangeBlock)
test_cmd_documents_context_anchor_window_size_3() {
    log_test "promptimize.md documents before_context and after_context up to 3 lines"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the ChangeBlock structure in Step 6a
    # When we check for context window size documentation
    # Then it specifies "up to 3" lines for both before and after context
    local context_3_count
    context_3_count=$(grep -c 'up to 3' "$PROMPTIMIZE_CMD" || true)
    if [[ "$context_3_count" -ge 2 ]]; then
        log_pass
    else
        log_fail "Expected at least 2 'up to 3' references (before + after context), found $context_3_count"
    fi
}

# derived_from: dimension:boundary (command documents 500 line and 5000 word thresholds in Step 6c)
test_cmd_documents_budget_thresholds_500_lines_5000_words() {
    log_test "promptimize.md Step 6c documents 500 line and 5,000 word budget thresholds"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the token budget check in Step 6c
    # When we check for the threshold values
    # Then it documents both 500 lines and 5,000 words
    if grep -q '500 lines' "$PROMPTIMIZE_CMD" && grep -q '5,000 words\|5000 words' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing 500 lines and 5,000 words budget thresholds"
    fi
}

# derived_from: dimension:boundary (rubric score range: Fail(1) is minimum, Pass(3) is maximum)
test_rubric_score_range_1_to_3() {
    log_test "scoring-rubric.md documents score range from Fail(1) to Pass(3) with no other values"
    if [[ ! -f "$RUBRIC_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the behavioral anchors table header
    # When we verify the score values
    # Then only 1, 2, 3 are defined (no 0 or 4)
    local header
    header=$(grep -E '^\| Dimension' "$RUBRIC_FILE" | head -1)
    if [[ "$header" == *"Fail (1)"* ]] && [[ "$header" == *"Pass (3)"* ]] && [[ "$header" != *"(0)"* ]] && [[ "$header" != *"(4)"* ]]; then
        log_pass
    else
        log_fail "Score range should be 1-3 only"
    fi
}


# ============================================================
# Dimension 3: Adversarial / Negative Testing
# ============================================================

# derived_from: dimension:adversarial-zero (guidelines Update Log has at least 1 entry)
test_guidelines_update_log_not_empty() {
    log_test "prompt-guidelines.md Update Log has at least 1 entry row"

    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    # After the "## Update Log" heading, count table rows (exclude header and separator)
    local log_rows
    log_rows=$(sed -n '/^## Update Log/,$ p' "$GUIDELINES_FILE" | grep -cE '^\| [0-9]{4}-' || true)
    if [[ "$log_rows" -ge 1 ]]; then
        log_pass
    else
        log_fail "Update Log has $log_rows date rows (expected >= 1)"
    fi
}

# derived_from: dimension:adversarial-data-integrity (rubric behavioral anchors has no empty cells)
test_rubric_no_empty_table_cells() {
    log_test "scoring-rubric.md behavioral anchors table has no empty cells"

    if [[ ! -f "$RUBRIC_FILE" ]]; then log_fail "File not found"; return; fi
    # Check for adjacent pipes with only whitespace between them (empty cell),
    # excluding separator rows (|---|---|)
    local empty_cells
    empty_cells=$(grep -E '^\|' "$RUBRIC_FILE" | grep -vE '^\|[-| ]+\|$' | grep -cE '\|\s*\|' || true)
    if [[ "$empty_cells" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $empty_cells empty table cell(s) in behavioral anchors"
    fi
}

# derived_from: dimension:adversarial-CRUD (SKILL.md has error handling for missing reference files)
test_skill_has_reference_file_error_handling() {
    log_test "SKILL.md documents error handling for missing reference files"

    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'not found\|error.*reference\|required reference' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing error handling for missing reference files"
    fi
}

# derived_from: dimension:adversarial (command validates score must be integer 1, 2, or 3 -- rejects 0 and 4)
test_cmd_validates_score_values_1_2_3_only() {
    log_test "promptimize.md Step 4c validates each dimension score is integer 1, 2, or 3"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Phase 1 validation rules
    # When we check for the score value constraint
    # Then it specifies "1, 2, or 3" as valid values
    if grep -q '1, 2, or 3' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing score value constraint '1, 2, or 3'"
    fi
}

# derived_from: dimension:adversarial (command lists all 9 canonical dimension names for validation)
test_cmd_lists_all_10_canonical_dimension_names() {
    log_test "promptimize.md Step 4c lists all 10 canonical dimension name values"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Phase 1 JSON validation listing canonical names
    # When we count the canonical snake_case names
    # Then all 10 are present
    local missing=0
    for name in "structure_compliance" "token_economy" "description_quality" "persuasion_strength" "technique_currency" "prohibition_clarity" "example_quality" "progressive_disclosure" "context_engineering" "cache_friendliness"; do
        if ! grep -q "$name" "$PROMPTIMIZE_CMD"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 10 canonical dimension names in promptimize.md"
    fi
}

# derived_from: dimension:adversarial (command validates suggestion non-null when score < 3)
test_cmd_validates_suggestion_non_null_when_score_below_3() {
    log_test "promptimize.md Step 4c validates suggestion must be non-null when score < 3"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the suggestion constraint in Phase 1 validation
    # When we check for the conditional requirement
    # Then it documents score < 3 requires non-null suggestion
    if grep -qi 'score.*<.*3.*suggestion.*non-null\|suggestion.*non-null.*score.*<.*3\|score < 3.*then.*suggestion' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing suggestion non-null constraint for score < 3"
    fi
}

# derived_from: dimension:adversarial (command validates suggestion must be null when score == 3)
test_cmd_validates_suggestion_null_when_score_3() {
    log_test "promptimize.md Step 4c validates suggestion must be null when score == 3"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the suggestion constraint in Phase 1 validation
    # When we check for the score-3 null requirement
    # Then it documents score == 3 requires null suggestion
    if grep -qi 'score.*==.*3.*suggestion.*null\|score == 3.*null' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing suggestion null constraint for score == 3"
    fi
}

# derived_from: dimension:adversarial (SKILL.md change tag attribute order is fixed: dimension then rationale)
test_skill_change_tag_attribute_order_fixed() {
    log_test "SKILL.md documents change tag attribute order: dimension first, rationale second"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the change tag format specification
    # When we check the documented attribute order
    # Then dimension appears before rationale in the tag example
    if grep -q 'dimension=.*rationale=' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing fixed attribute order (dimension then rationale) in change tag"
    fi
}

# derived_from: dimension:adversarial (command documents reversed attribute order as validation failure)
test_cmd_reversed_attribute_order_fails_validation() {
    log_test "promptimize.md documents reversed attribute order as tag validation failure"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the tag validation regex in Step 6a
    # When we check for the reversed-order handling
    # Then it documents reversed attributes cause validation failure
    if grep -qi 'reversed attribute order\|rationale=.*dimension=' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing reversed attribute order validation documentation"
    fi
}

# derived_from: dimension:adversarial (command documents nested change tags not allowed)
test_cmd_documents_no_nested_change_tags() {
    log_test "promptimize.md documents change tags must not be nested"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the tag validation checks in Step 6a
    # When we check for the nesting prohibition
    # Then it documents "not nested" or no nesting constraint
    if grep -qi 'not nested\|no.*nested\|are not nested' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing no-nesting constraint for change tags"
    fi
}

# derived_from: dimension:adversarial (command documents anchor match failure with zero/multiple matches)
test_cmd_anchor_match_reports_zero_and_multiple_match_failures() {
    log_test "promptimize.md match_anchors_in_original reports zero-match and multiple-match failures"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the match_anchors_in_original sub-procedure
    # When we check for both failure cases
    # Then it documents both "zero matches" and "multiple matches" return paths
    if grep -qi 'zero match\|not found in original' "$PROMPTIMIZE_CMD" && grep -qi 'multiple.*match\|matched multiple' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing zero-match or multiple-match failure documentation"
    fi
}

# derived_from: dimension:adversarial (SKILL.md documents overlapping dimensions use comma-separated format)
test_skill_documents_comma_separated_overlapping_dimensions() {
    log_test "SKILL.md documents comma-separated dimension names for overlapping changes"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the change tag format documentation
    # When we check for comma-separated dimension handling
    # Then it documents comma-separated format for overlapping dimensions
    if grep -q 'comma-separated' "$SKILL_FILE" || grep -q 'dimension=".*,.*"' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing comma-separated overlapping dimension documentation"
    fi
}

# derived_from: dimension:adversarial (command ignores change tags inside code fences)
test_cmd_ignores_change_tags_inside_code_fences() {
    log_test "promptimize.md documents ignoring change/close tags inside code fences"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the tag validation in Step 6a
    # When we check for code fence state tracking
    # Then it documents tracking in_fence state and ignoring tags within fences
    if grep -q 'in_fence' "$PROMPTIMIZE_CMD" && grep -qi 'ignore.*change\|in_fence.*true.*ignore' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing code fence handling for change tag validation"
    fi
}


# ============================================================
# Dimension 4: Error Propagation & Failure Modes
# ============================================================

# derived_from: design:error-contract (SKILL.md documents STOP on invalid path)
test_skill_stops_on_invalid_path() {
    log_test "SKILL.md documents STOP on invalid component path"

    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q 'STOP' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing STOP directive for invalid path"
    fi
}

# derived_from: design:error-contract (refresh command documents STOP on file not found)
test_refresh_cmd_stops_on_missing_file() {
    log_test "refresh-prompt-guidelines.md documents STOP on file not found"

    if [[ ! -f "$REFRESH_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'STOP' "$REFRESH_CMD"; then
        log_pass
    else
        log_fail "Missing STOP directive for file not found"
    fi
}

# derived_from: design:error-contract (command documents tag_validation_failed fallback)
test_cmd_has_malformed_marker_fallback() {
    log_test "promptimize.md documents tag_validation_failed fallback for Accept-some"

    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'tag_validation_failed' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing tag_validation_failed fallback documentation"
    fi
}

# derived_from: design:error-contract (promptimize.md command handles empty file discovery)
test_promptimize_cmd_handles_empty_results() {
    log_test "promptimize.md documents handling when no files found"

    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'no.*found\|No.*files found\|STOP' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing empty results handling"
    fi
}

# derived_from: design:error-contract (refresh command documents unparseable agent output)
test_refresh_cmd_handles_unparseable_output() {
    log_test "refresh-prompt-guidelines.md documents unparseable agent output fallback"

    if [[ ! -f "$REFRESH_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'unparseable\|parse.*fail\|cannot be parsed' "$REFRESH_CMD"; then
        log_pass
    else
        log_fail "Missing unparseable output fallback documentation"
    fi
}

# derived_from: design:error-contract (command Step 4c documents Phase 1 JSON parse failure with STOP)
test_cmd_phase1_parse_failure_stops() {
    log_test "promptimize.md documents Phase 1 JSON parse failure displays error and STOPs"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Phase 1 parsing section
    # When we check for the parse failure handling
    # Then it documents displaying an error with first 200 chars and STOP
    if grep -qi 'validation failed\|Phase 1 JSON validation failed' "$PROMPTIMIZE_CMD" && grep -q 'STOP' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing Phase 1 parse failure -> STOP documentation"
    fi
}

# derived_from: design:error-contract (command Step 2.5 documents file read failure with STOP)
test_cmd_file_read_failure_stops() {
    log_test "promptimize.md Step 2.5 documents file read failure with STOP"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the file read step
    # When we check for the read failure error path
    # Then it documents error display and STOP
    if grep -qi 'could not read target file\|file read fails' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing file read failure -> STOP documentation"
    fi
}

# derived_from: design:error-contract (command documents accept some gated by BOTH tag_validation_failed AND drift_detected)
test_cmd_accept_some_gated_by_both_flags() {
    log_test "promptimize.md Accept some requires BOTH tag_validation_failed=false AND drift_detected=false"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the approval menu option gating
    # When we check for both conditions
    # Then both tag_validation_failed and drift_detected are referenced as gating conditions
    if grep -q 'tag_validation_failed.*false' "$PROMPTIMIZE_CMD" && grep -q 'drift_detected.*false' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing dual-flag gating for Accept some"
    fi
}

# derived_from: design:error-contract (command Step 6b skips drift detection when tag validation failed)
test_cmd_drift_detection_skipped_when_tag_validation_failed() {
    log_test "promptimize.md Step 6b skips drift detection when tag_validation_failed is true"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the drift detection step
    # When we check for the skip condition
    # Then it documents skipping when tag_validation_failed is true
    if grep -qi 'Skip.*tag_validation_failed.*true\|tag_validation_failed.*true.*skip\|Skip this step if.*tag_validation_failed' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing skip drift detection when tag_validation_failed"
    fi
}

# derived_from: design:error-contract (command Step 8a score 100 with change blocks shows warning)
test_cmd_score_100_with_change_blocks_warns() {
    log_test "promptimize.md Step 8a warns when score 100 but ChangeBlocks exist"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the approval path determination
    # When we check for the edge case of score 100 + change blocks
    # Then it documents a warning about potential grading error
    if grep -qi 'grading error\|Score is 100 but change blocks' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing score 100 + change blocks warning"
    fi
}

# derived_from: design:error-contract (command Step 8a score < 100 with zero change blocks shows note)
test_cmd_score_below_100_zero_changes_shows_note() {
    log_test "promptimize.md Step 8a notes when score < 100 but zero ChangeBlocks"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the approval path determination
    # When we check for the no-changes-generated case
    # Then it documents a note and STOP
    if grep -qi 'no changes were generated\|scored partial.*fail.*but no changes' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing score < 100 + zero changes note"
    fi
}

# derived_from: design:error-contract (accept some anchor match failure degrades to accept all / reject)
test_cmd_accept_some_anchor_failure_degrades() {
    log_test "promptimize.md Accept some anchor match failure degrades to Accept all/Reject"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Accept some handler Part 2
    # When we check for anchor match failure fallback
    # Then it documents degradation to two-option menu
    if grep -qi 'could not uniquely match\|Degrade to Accept all.*Reject\|re-presenting.*two-option' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing anchor match failure degradation in Accept some"
    fi
}


# ============================================================
# Dimension 5: Mutation Mindset (behavioral pinning)
# ============================================================

# derived_from: dimension:mutation-line-deletion (9 specific dimension NAMES present in SKILL.md)
test_skill_lists_all_10_dimension_names() {
    log_test "SKILL.md lists all 10 evaluation dimension names"

    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    local missing=0
    for dim in "Structure compliance" "Token economy" "Description quality" "Persuasion strength" "Technique currency" "Prohibition clarity" "Example quality" "Progressive disclosure" "Context engineering" "Cache friendliness"; do
        if ! grep -q "$dim" "$SKILL_FILE"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 10 dimension names in SKILL.md"
    fi
}

# derived_from: dimension:mutation-return-value (promptimize.md report template includes key output fields)
test_skill_report_template_has_required_fields() {
    log_test "promptimize.md report template includes overall score and component type"

    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'overall_score\|Overall score' "$PROMPTIMIZE_CMD" && grep -qi 'component_type\|Component type' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Report template missing 'overall_score/Overall score' or 'component_type/Component type' fields"
    fi
}

# derived_from: dimension:mutation-logic-inversion (promptimize.md distinguishes pass from partial/fail in issue table)
test_skill_severity_mapping_documented() {
    log_test "promptimize.md documents severity mapping (fail=blocker, partial=warning)"

    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'blocker' "$PROMPTIMIZE_CMD" && grep -q 'warning' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing severity mapping documentation"
    fi
}

# derived_from: dimension:mutation-line-deletion (guidelines sections subsection structure intact)
test_guidelines_has_skills_subsection() {
    log_test "prompt-guidelines.md Plugin-Specific Patterns has Skills subsection"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '### Skills' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing ### Skills subsection"; fi
}

test_guidelines_has_agents_subsection() {
    log_test "prompt-guidelines.md Plugin-Specific Patterns has Agents subsection"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '### Agents' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing ### Agents subsection"; fi
}

test_guidelines_has_commands_subsection() {
    log_test "prompt-guidelines.md Plugin-Specific Patterns has Commands subsection"
    if [[ ! -f "$GUIDELINES_FILE" ]]; then log_fail "File not found"; return; fi
    if grep -q '### Commands' "$GUIDELINES_FILE"; then log_pass; else log_fail "Missing ### Commands subsection"; fi
}

# derived_from: dimension:mutation-arithmetic (score formula explicitly uses /30 and *100)
test_cmd_score_formula_contains_30_and_100() {
    log_test "promptimize.md score formula documents both /30 divisor and *100 multiplier"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the score computation step
    # When we check for both constants
    # Then the formula references both 30 and 100
    if grep -q '30' "$PROMPTIMIZE_CMD" && grep -q '100' "$PROMPTIMIZE_CMD" && grep -qi 'round' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing formula components (30, 100, round)"
    fi
}

# derived_from: dimension:mutation-logic-inversion (accept some keeps original text for unselected dimensions)
test_cmd_accept_some_unselected_retain_original() {
    log_test "promptimize.md Accept some Part 3 documents unselected dimensions retain original text"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the replacement assembly section
    # When we check for unselected dimension handling
    # Then it documents that unselected regions keep original content
    if grep -qi 'Unselected.*retain.*original\|original.*text.*unselected\|no replacement applied' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing unselected dimensions retain original documentation"
    fi
}

# derived_from: dimension:mutation-line-deletion (accept some applies simultaneous replacement not sequential)
test_cmd_accept_some_simultaneous_replacement() {
    log_test "promptimize.md Accept some documents simultaneous (not sequential) replacement"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the replacement assembly section Part 3
    # When we check for the simultaneous constraint
    # Then it documents simultaneous application to avoid line-offset drift
    if grep -qi 'simultaneously\|not sequentially\|line-offset drift' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing simultaneous replacement documentation"
    fi
}

# derived_from: dimension:mutation-line-deletion (accept some strips residual change tags as defensive pass)
test_cmd_accept_some_residual_tag_stripping() {
    log_test "promptimize.md Accept some Part 4 strips residual <change> tags defensively"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the assembly and write section Part 4
    # When we check for the residual tag stripping
    # Then it documents a defensive final pass for stray tags
    if grep -qi 'residual.*<change>\|Strip any residual\|defensive final pass\|stray tags' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing residual tag stripping documentation"
    fi
}

# derived_from: dimension:mutation-return-value (SKILL.md pass dimensions produce no change tags in phase2)
test_skill_pass_dimensions_no_change_tags() {
    log_test "SKILL.md documents pass dimensions (score=3) produce no change tags in phase 2"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the phase 2 tag rules
    # When we check for the pass-dimension rule
    # Then it documents "Do NOT add <change> tags" for score=3
    if grep -qi 'Pass.*score.*3.*Do NOT\|score=3.*Do NOT.*change\|Pass dimensions.*Do NOT' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing pass-dimension no-change-tag rule"
    fi
}

# derived_from: dimension:mutation-line-deletion (command merge-adjacent flag documented in match_anchors_in_original)
test_cmd_merge_adjacent_flag_documented() {
    log_test "promptimize.md match_anchors_in_original documents merge_adjacent flag"
    if [[ ! -f "$PROMPTIMIZE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the sub-procedure definition
    # When we check for merge_adjacent parameter
    # Then it documents the flag and its effect on adjacent blocks
    if grep -q 'merge_adjacent\|merge-adjacent' "$PROMPTIMIZE_CMD"; then
        log_pass
    else
        log_fail "Missing merge_adjacent flag documentation"
    fi
}

# derived_from: dimension:mutation-logic-inversion (SKILL.md documents preservation: text outside change tags identical to original)
test_skill_preservation_rule_documented() {
    log_test "SKILL.md documents text outside change tags must be identical to original"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the phase 2 tag rules
    # When we check for the preservation constraint
    # Then it documents text outside tags must be identical to original
    if grep -qi 'outside.*change.*tags.*identical\|identical to the original\|Preservation' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing preservation rule for text outside change tags"
    fi
}

# derived_from: dimension:mutation-line-deletion (SKILL.md canonical dimension name mapping table has all 9 snake_case names)
test_skill_canonical_name_mapping_table_has_10_entries() {
    log_test "SKILL.md canonical dimension name mapping table has all 10 snake_case entries"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the canonical dimension name mapping table
    # When we count the snake_case JSON name values
    # Then all 10 are present
    local missing=0
    for name in "structure_compliance" "token_economy" "description_quality" "persuasion_strength" "technique_currency" "prohibition_clarity" "example_quality" "progressive_disclosure" "context_engineering" "cache_friendliness"; do
        if ! grep -q "$name" "$SKILL_FILE"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 10 canonical snake_case dimension names in SKILL.md"
    fi
}

# derived_from: dimension:mutation-logic-inversion (PROHIBITED section in SKILL.md pins scoring against rubric)
test_skill_prohibited_section_pins_scoring_to_rubric() {
    log_test "SKILL.md PROHIBITED section forbids scoring without referencing rubric"
    if [[ ! -f "$SKILL_FILE" ]]; then log_fail "File not found"; return; fi
    # Given the PROHIBITED section
    # When we check for the rubric-based scoring constraint
    # Then it forbids scoring without referencing behavioral anchors
    if grep -q '## PROHIBITED' "$SKILL_FILE" && grep -qi 'behavioral anchors\|scoring-rubric' "$SKILL_FILE"; then
        log_pass
    else
        log_fail "Missing PROHIBITED constraint about rubric-based scoring"
    fi
}


# ============================================================
# Integration: validate.sh passes for all new files
# ============================================================

# derived_from: spec:AC-validate (all new files pass structural validation with 0 errors)
test_validate_sh_passes() {
    log_test "validate.sh passes with 0 errors (integration)"

    cd "$PROJECT_ROOT"
    local output exit_code=0
    output=$(bash ./validate.sh 2>&1) || exit_code=$?
    if [[ "$exit_code" -eq 0 ]]; then
        log_pass
    else
        log_fail "validate.sh exited with code $exit_code"
    fi
    cd "$SCRIPT_DIR"
}


# ============================================================
# Run all tests
# ============================================================
main() {
    echo "=========================================="
    echo "Promptimize Content Regression Tests"
    echo "=========================================="
    echo ""

    echo "--- Dimension 1: BDD Scenarios ---"
    echo ""

    # scoring-rubric.md
    test_rubric_has_exactly_10_dimensions
    test_rubric_has_pass_partial_fail_columns
    test_rubric_has_component_type_applicability_table
    test_rubric_has_auto_pass_entries
    test_rubric_applicability_has_three_component_columns

    # prompt-guidelines.md
    test_guidelines_has_last_updated_date
    test_guidelines_has_at_least_15_guidelines
    test_guidelines_has_core_principles_section
    test_guidelines_has_plugin_specific_patterns_section
    test_guidelines_has_persuasion_techniques_section
    test_guidelines_has_techniques_by_evidence_tier_section
    test_guidelines_has_anti_patterns_section
    test_guidelines_has_update_log_section

    # SKILL.md
    test_skill_uses_xml_not_html_markers
    test_cmd_has_all_approval_options
    test_skill_handles_skill_type
    test_skill_handles_agent_type
    test_skill_handles_command_type
    test_skill_documents_invalid_path_error
    test_skill_documents_staleness_warning
    test_skill_has_phase1_output_tags
    test_skill_has_phase2_output_tags
    test_skill_has_grading_result_block
    test_skill_phase1_documents_dimensions_array
    test_cmd_accept_some_uses_multiselect_for_dimension_selection
    test_cmd_malformed_tags_degrade_to_two_option_menu
    test_cmd_accept_all_strips_change_tags
    test_skill_auto_pass_sets_score_3_and_null_suggestion
    test_cmd_yolo_auto_selects_accept_all
    test_cmd_report_includes_staleness_warning_template
    test_cmd_report_includes_over_budget_warning
    test_cmd_drift_detected_disables_accept_some
    test_cmd_score_100_no_changes_skips_approval
    test_skill_suggestion_required_when_score_below_3
    test_cmd_strengths_section_excludes_auto_passed
    test_cmd_issues_table_blockers_before_warnings
    test_cmd_overlapping_dimensions_single_option

    # promptimize.md command
    test_promptimize_cmd_delegates_to_skill
    test_promptimize_cmd_asks_component_type
    test_cmd_has_score_computation
    test_cmd_has_drift_detection
    test_cmd_has_tag_validation
    test_cmd_has_yolo_mode_handling

    # refresh-prompt-guidelines.md command
    test_refresh_cmd_documents_websearch_fallback
    test_refresh_cmd_documents_deduplication
    test_refresh_cmd_documents_changelog_update
    test_refresh_cmd_lists_all_6_sections

    echo ""
    echo "--- Dimension 2: Boundary Values ---"
    echo ""

    test_skill_under_500_lines
    test_scoring_formula_max_denominator_is_30
    test_cmd_validates_exactly_10_dimensions_in_phase1
    test_cmd_documents_context_anchor_window_size_3
    test_cmd_documents_budget_thresholds_500_lines_5000_words
    test_rubric_score_range_1_to_3

    echo ""
    echo "--- Dimension 3: Adversarial / Negative ---"
    echo ""

    test_guidelines_update_log_not_empty
    test_rubric_no_empty_table_cells
    test_skill_has_reference_file_error_handling
    test_cmd_validates_score_values_1_2_3_only
    test_cmd_lists_all_10_canonical_dimension_names
    test_cmd_validates_suggestion_non_null_when_score_below_3
    test_cmd_validates_suggestion_null_when_score_3
    test_skill_change_tag_attribute_order_fixed
    test_cmd_reversed_attribute_order_fails_validation
    test_cmd_documents_no_nested_change_tags
    test_cmd_anchor_match_reports_zero_and_multiple_match_failures
    test_skill_documents_comma_separated_overlapping_dimensions
    test_cmd_ignores_change_tags_inside_code_fences

    echo ""
    echo "--- Dimension 4: Error Propagation ---"
    echo ""

    test_skill_stops_on_invalid_path
    test_refresh_cmd_stops_on_missing_file
    test_cmd_has_malformed_marker_fallback
    test_promptimize_cmd_handles_empty_results
    test_refresh_cmd_handles_unparseable_output
    test_cmd_phase1_parse_failure_stops
    test_cmd_file_read_failure_stops
    test_cmd_accept_some_gated_by_both_flags
    test_cmd_drift_detection_skipped_when_tag_validation_failed
    test_cmd_score_100_with_change_blocks_warns
    test_cmd_score_below_100_zero_changes_shows_note
    test_cmd_accept_some_anchor_failure_degrades

    echo ""
    echo "--- Dimension 5: Mutation Mindset ---"
    echo ""

    test_skill_lists_all_10_dimension_names
    test_skill_report_template_has_required_fields
    test_skill_severity_mapping_documented
    test_guidelines_has_skills_subsection
    test_guidelines_has_agents_subsection
    test_guidelines_has_commands_subsection
    test_cmd_score_formula_contains_30_and_100
    test_cmd_accept_some_unselected_retain_original
    test_cmd_accept_some_simultaneous_replacement
    test_cmd_accept_some_residual_tag_stripping
    test_skill_pass_dimensions_no_change_tags
    test_cmd_merge_adjacent_flag_documented
    test_skill_preservation_rule_documented
    test_skill_canonical_name_mapping_table_has_10_entries
    test_skill_prohibited_section_pins_scoring_to_rubric

    echo ""
    echo "--- Integration ---"
    echo ""

    test_validate_sh_passes

    echo ""
    echo "=========================================="
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed"
    if [[ $TESTS_FAILED -gt 0 ]]; then
        echo -e "${RED}Failed: ${TESTS_FAILED}${NC}"
    fi
    echo "=========================================="

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main
