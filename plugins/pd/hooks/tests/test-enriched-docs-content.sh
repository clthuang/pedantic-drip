#!/usr/bin/env bash
# Content regression and hook integration tests for the enriched-documentation-phase feature
# Run: bash plugins/pd/hooks/tests/test-enriched-docs-content.sh
#
# Tests verify:
# - doc_tiers config injection in session-start.sh (shell hook)
# - doc-schema.md structural integrity (content regression)
# - SYNC marker presence and pairing across files (content regression)
# - YAML frontmatter and required sections in commands/agents/skills (content regression)
# - Section marker template validity in doc-schema (content regression)
# - Agent constraint contracts (read-only, tools, output format) (content regression)
# - Dispatch budget documentation (content regression)

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
TESTS_SKIPPED=0

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

log_skip() {
    echo -e "${YELLOW}  SKIP: $1${NC}"
    ((TESTS_SKIPPED++)) || true
    ((TESTS_RUN--)) || true
}

# --- Paths ---
PLUGIN_DIR="${PROJECT_ROOT}/plugins/pd"
DOC_SCHEMA="${PLUGIN_DIR}/references/doc-schema.md"
RESEARCHER_AGENT="${PLUGIN_DIR}/agents/documentation-researcher.md"
WRITER_AGENT="${PLUGIN_DIR}/agents/documentation-writer.md"
UPDATING_DOCS_SKILL="${PLUGIN_DIR}/skills/updating-docs/SKILL.md"
GENERATE_DOCS_CMD="${PLUGIN_DIR}/commands/generate-docs.md"
FINISH_FEATURE_CMD="${PLUGIN_DIR}/commands/finish-feature.md"
WRAP_UP_CMD="${PLUGIN_DIR}/commands/wrap-up.md"

# --- YOLO test helpers (shared with test-hooks.sh) ---
YOLO_TMPDIR=""

setup_yolo_test() {
    YOLO_TMPDIR=$(mktemp -d)
    mkdir -p "${YOLO_TMPDIR}/.git" "${YOLO_TMPDIR}/.claude"
}

teardown_yolo_test() {
    if [[ -n "$YOLO_TMPDIR" ]]; then
        cd "${PROJECT_ROOT}"
        rm -rf "$YOLO_TMPDIR"
        YOLO_TMPDIR=""
    fi
}


# ============================================================
# Dimension 1: BDD Scenarios — doc_tiers config injection
# ============================================================

# derived_from: spec:AC-1 (session-start injects pd_doc_tiers with default value)
# Anticipate: If the doc_tiers injection line was deleted from session-start.sh,
# no doc_tiers value would appear in the context output.
test_session_start_injects_doc_tiers_default() {
    log_test "session-start injects pd_doc_tiers with default value"

    # Given a project with no doc_tiers configured
    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
artifacts_root: docs
---
TMPL

    # When session-start runs
    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    # Then the output contains pd_doc_tiers with the default value
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_doc_tiers: user-guide,dev-guide,technical' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_doc_tiers: user-guide,dev-guide,technical in context"
    fi

    teardown_yolo_test
}

# derived_from: spec:AC-2 (session-start injects custom doc_tiers from config)
# Anticipate: If read_local_md_field ignores the doc_tiers field or the injection
# line uses the wrong field name, custom values would not appear.
test_session_start_injects_custom_doc_tiers() {
    log_test "session-start injects custom doc_tiers from config"

    # Given a project with custom doc_tiers
    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
doc_tiers: user-guide,technical
---
TMPL

    # When session-start runs
    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    # Then the output reflects the custom tiers
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_doc_tiers: user-guide,technical' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_doc_tiers: user-guide,technical in context"
    fi

    teardown_yolo_test
}

# derived_from: spec:AC-3 (session-start injects single-tier doc_tiers)
# Anticipate: Edge case — single tier with no commas might be mishandled
# if the injection code assumes comma-separated input.
test_session_start_injects_single_tier() {
    log_test "session-start injects single-tier doc_tiers"

    # Given a project with only one tier
    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
doc_tiers: technical
---
TMPL

    # When session-start runs
    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    # Then it shows only the single tier
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); ctx = d['hookSpecificOutput']['additionalContext']; assert 'pd_doc_tiers: technical' in ctx" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_doc_tiers: technical in context"
    fi

    teardown_yolo_test
}

# derived_from: spec:AC-4 (session-start output with doc_tiers is valid JSON)
# Anticipate: If special characters in the doc_tiers value break JSON escaping,
# the entire hook output would be invalid JSON.
test_session_start_doc_tiers_valid_json() {
    log_test "session-start produces valid JSON with doc_tiers present"

    # Given a standard config
    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
doc_tiers: user-guide,dev-guide,technical
---
TMPL

    # When session-start runs
    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    # Then the output is valid JSON
    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Invalid JSON output with doc_tiers"
    fi

    teardown_yolo_test
}


# ============================================================
# Dimension 1: BDD Scenarios — doc-schema.md structure
# ============================================================

# derived_from: spec:AC-5 (doc-schema defines exactly 3 tiers)
# Anticipate: If a tier heading is deleted or renamed, downstream tools
# that parse by heading name would fail to find the tier.
test_doc_schema_defines_three_tiers() {
    log_test "doc-schema.md defines exactly 3 documentation tiers"

    # Given the doc-schema file exists
    if [[ ! -f "$DOC_SCHEMA" ]]; then
        log_fail "File not found: $DOC_SCHEMA"
        return
    fi
    # When we count tier headings (## user-guide, ## dev-guide, ## technical)
    local tier_count=0
    grep -q '^## user-guide' "$DOC_SCHEMA" && ((tier_count++)) || true
    grep -q '^## dev-guide' "$DOC_SCHEMA" && ((tier_count++)) || true
    grep -q '^## technical' "$DOC_SCHEMA" && ((tier_count++)) || true
    # Then there are exactly 3
    if [[ "$tier_count" -eq 3 ]]; then
        log_pass
    else
        log_fail "Expected 3 tier headings, found $tier_count"
    fi
}

# derived_from: spec:AC-6 (doc-schema has YAML Frontmatter Template section)
# Anticipate: Without this section, the writer agent would not know
# how to format frontmatter, causing inconsistent doc output.
test_doc_schema_has_yaml_frontmatter_template() {
    log_test "doc-schema.md has YAML Frontmatter Template section"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q '## YAML Frontmatter Template' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing '## YAML Frontmatter Template' section"
    fi
}

# derived_from: spec:AC-7 (doc-schema has Section Marker Template section)
# Anticipate: Without this section, auto-generated content boundaries
# would be undefined, risking overwrite of manual edits.
test_doc_schema_has_section_marker_template() {
    log_test "doc-schema.md has Section Marker Template section"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Section Marker Template' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing '## Section Marker Template' section"
    fi
}

# derived_from: spec:AC-8 (doc-schema has Tier-to-Source Monitoring section)
# Anticipate: Without monitoring paths, drift detection cannot determine
# which source changes affect which tier.
test_doc_schema_has_tier_to_source_monitoring() {
    log_test "doc-schema.md has Tier-to-Source Monitoring section"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Tier-to-Source Monitoring' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing '## Tier-to-Source Monitoring' section"
    fi
}

# derived_from: spec:AC-9 (doc-schema has Project-Type Additions section)
# Anticipate: Without project-type additions, the writer cannot add
# type-specific files (e.g., plugin-api.md for Plugin projects).
test_doc_schema_has_project_type_additions() {
    log_test "doc-schema.md has Project-Type Additions section"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Project-Type Additions' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing '## Project-Type Additions' section"
    fi
}

# derived_from: spec:AC-10 (doc-schema has Workflow Artifacts Index Format)
test_doc_schema_has_workflow_artifacts_index() {
    log_test "doc-schema.md has Workflow Artifacts Index Format section"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Workflow Artifacts Index Format' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing '## Workflow Artifacts Index Format' section"
    fi
}

# derived_from: spec:AC-11 (doc-schema section markers use AUTO-GENERATED delimiters)
# Anticipate: If the marker format changes, the writer agent's regex
# for detecting existing markers would break.
test_doc_schema_section_markers_use_auto_generated() {
    log_test "doc-schema.md section markers use AUTO-GENERATED delimiters"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q 'AUTO-GENERATED: START' "$DOC_SCHEMA" && grep -q 'AUTO-GENERATED: END' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing AUTO-GENERATED START/END markers in template"
    fi
}

# derived_from: spec:AC-12 (doc-schema frontmatter template has last-updated and source-feature)
# Anticipate: If a required frontmatter field is removed, drift detection
# would have no timestamp to compare against.
test_doc_schema_frontmatter_has_required_fields() {
    log_test "doc-schema.md frontmatter template has last-updated and source-feature"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    if grep -q 'last-updated' "$DOC_SCHEMA" && grep -q 'source-feature' "$DOC_SCHEMA"; then
        log_pass
    else
        log_fail "Missing last-updated or source-feature in frontmatter template"
    fi
}


# ============================================================
# Dimension 1: BDD Scenarios — agent/command content
# ============================================================

# derived_from: spec:AC-13 (researcher agent is read-only — tools list has no Write/Edit/Bash)
# Anticipate: If Write, Edit, or Bash is added to the tools list,
# the researcher could modify files, violating its read-only contract.
test_researcher_agent_is_read_only() {
    log_test "documentation-researcher agent has read-only tools (no Write/Edit/Bash)"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given the tools line in frontmatter
    local tools_line
    tools_line=$(grep '^tools:' "$RESEARCHER_AGENT" | head -1)
    # Then it does NOT contain Write, Edit, or Bash
    if echo "$tools_line" | grep -qE 'Write|Edit|Bash'; then
        log_fail "Researcher has write tools: $tools_line"
    else
        log_pass
    fi
}

# derived_from: spec:AC-14 (researcher agent has correct tools)
test_researcher_agent_has_read_tools() {
    log_test "documentation-researcher agent has Read, Glob, Grep tools"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    local tools_line
    tools_line=$(grep '^tools:' "$RESEARCHER_AGENT" | head -1)
    if echo "$tools_line" | grep -q 'Read' && echo "$tools_line" | grep -q 'Glob' && echo "$tools_line" | grep -q 'Grep'; then
        log_pass
    else
        log_fail "Missing Read/Glob/Grep tools: $tools_line"
    fi
}

# derived_from: spec:AC-15 (writer agent has write tools)
test_writer_agent_has_write_tools() {
    log_test "documentation-writer agent has Write and Edit tools"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    local tools_line
    tools_line=$(grep '^tools:' "$WRITER_AGENT" | head -1)
    if echo "$tools_line" | grep -q 'Write' && echo "$tools_line" | grep -q 'Edit'; then
        log_pass
    else
        log_fail "Missing Write/Edit tools: $tools_line"
    fi
}

# derived_from: spec:AC-16 (researcher documents three-tier discovery in Step 1b)
# Anticipate: If Step 1b is deleted, researcher would not probe for tier directories,
# and tier_status output would be empty.
test_researcher_has_three_tier_discovery() {
    log_test "documentation-researcher has Three-Tier Doc Discovery step"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Three-Tier Doc Discovery' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing Three-Tier Doc Discovery section"
    fi
}

# derived_from: spec:AC-17 (researcher documents frontmatter drift detection)
test_researcher_has_frontmatter_drift_detection() {
    log_test "documentation-researcher has Frontmatter Drift Detection step"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Frontmatter Drift Detection' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing Frontmatter Drift Detection section"
    fi
}

# derived_from: spec:AC-18 (researcher output schema includes tier_status, affected_tiers, tier_drift)
# Anticipate: If any of these output fields is deleted from the schema example,
# downstream writer dispatches would not receive tier-level data.
test_researcher_output_has_tier_fields() {
    log_test "documentation-researcher output schema has tier_status, affected_tiers, tier_drift"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    local missing=0
    grep -q '"tier_status"' "$RESEARCHER_AGENT" || ((missing++)) || true
    grep -q '"affected_tiers"' "$RESEARCHER_AGENT" || ((missing++)) || true
    grep -q '"tier_drift"' "$RESEARCHER_AGENT" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 3 tier output fields in researcher schema"
    fi
}

# derived_from: spec:AC-19 (writer documents section marker handling)
test_writer_has_section_marker_handling() {
    log_test "documentation-writer has Section Marker Handling section"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Section Marker Handling' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing Section Marker Handling section"
    fi
}

# derived_from: spec:AC-20 (writer documents YAML frontmatter handling)
test_writer_has_yaml_frontmatter_handling() {
    log_test "documentation-writer has YAML Frontmatter Handling section"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '## YAML Frontmatter Handling' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing YAML Frontmatter Handling section"
    fi
}

# derived_from: spec:AC-21 (writer documents ADR Extraction section)
test_writer_has_adr_extraction() {
    log_test "documentation-writer has ADR Extraction section"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '## ADR Extraction' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing ADR Extraction section"
    fi
}

# derived_from: spec:AC-22 (writer documents tier-specific generation guidance)
test_writer_has_tier_specific_guidance() {
    log_test "documentation-writer has tier-specific generation guidance for all 3 tiers"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    local missing=0
    grep -q '### user-guide tier' "$WRITER_AGENT" || ((missing++)) || true
    grep -q '### dev-guide tier' "$WRITER_AGENT" || ((missing++)) || true
    grep -q '### technical tier' "$WRITER_AGENT" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 3 tier-specific guidance sections"
    fi
}

# derived_from: spec:AC-23 (generate-docs command has YAML frontmatter with description)
test_generate_docs_has_frontmatter() {
    log_test "generate-docs.md has YAML frontmatter with description"

    if [[ ! -f "$GENERATE_DOCS_CMD" ]]; then log_fail "File not found"; return; fi
    if head -1 "$GENERATE_DOCS_CMD" | grep -q '^---$' && grep -q '^description:' "$GENERATE_DOCS_CMD"; then
        log_pass
    else
        log_fail "Missing YAML frontmatter or description field"
    fi
}


# ============================================================
# Dimension 2: Boundary Values
# ============================================================

# derived_from: dimension:boundary (doc-schema user-guide tier lists exactly 3 files)
# Anticipate: If a file entry is deleted, scaffold mode would create
# an incomplete tier directory.
test_doc_schema_user_guide_has_3_files() {
    log_test "doc-schema.md user-guide tier lists exactly 3 files"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    # Count lines starting with "- " between ## user-guide and the next ## heading
    local count
    count=$(sed -n '/^## user-guide$/,/^## /p' "$DOC_SCHEMA" | grep -c '^- ' || true)
    if [[ "$count" -eq 3 ]]; then
        log_pass
    else
        log_fail "Expected 3 files in user-guide tier, found $count"
    fi
}

# derived_from: dimension:boundary (doc-schema dev-guide tier lists exactly 3 files)
test_doc_schema_dev_guide_has_3_files() {
    log_test "doc-schema.md dev-guide tier lists exactly 3 files"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    local count
    count=$(sed -n '/^## dev-guide$/,/^## /p' "$DOC_SCHEMA" | grep -c '^- ' || true)
    if [[ "$count" -eq 3 ]]; then
        log_pass
    else
        log_fail "Expected 3 files in dev-guide tier, found $count"
    fi
}

# derived_from: dimension:boundary (doc-schema technical tier lists exactly 4 files)
test_doc_schema_technical_has_4_files() {
    log_test "doc-schema.md technical tier lists exactly 4 files"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    local count
    count=$(sed -n '/^## technical$/,/^## /p' "$DOC_SCHEMA" | grep -c '^- ' || true)
    if [[ "$count" -eq 4 ]]; then
        log_pass
    else
        log_fail "Expected 4 files in technical tier, found $count"
    fi
}

# derived_from: dimension:boundary (ADR numbering format uses 3-digit zero-padded numbers)
# Anticipate: If the format changes to 2-digit, existing ADRs and the
# sequential numbering scan would break.
test_writer_adr_numbering_is_three_digit() {
    log_test "documentation-writer ADR numbering uses NNN (3-digit format)"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Check that the format spec mentions 3-digit zero-padded
    if grep -q 'zero-padded 3-digit' "$WRITER_AGENT" || grep -q 'ADR-{NNN}' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing 3-digit zero-padded numbering specification"
    fi
}

# derived_from: dimension:boundary (section marker pairs must have START and END)
# Anticipate: If the marker format has START without END (or vice versa),
# the writer's content replacement logic would corrupt files.
test_doc_schema_markers_are_paired() {
    log_test "doc-schema.md section markers are paired (START and END both present)"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    local start_count end_count
    start_count=$(grep -c 'AUTO-GENERATED: START' "$DOC_SCHEMA" || true)
    end_count=$(grep -c 'AUTO-GENERATED: END' "$DOC_SCHEMA" || true)
    if [[ "$start_count" -gt 0 ]] && [[ "$start_count" -eq "$end_count" ]]; then
        log_pass
    else
        log_fail "Marker mismatch: $start_count START vs $end_count END"
    fi
}

# derived_from: dimension:boundary (updating-docs SKILL.md under 500 lines)
test_updating_docs_skill_under_500_lines() {
    log_test "updating-docs/SKILL.md is under 500 lines"

    if [[ ! -f "$UPDATING_DOCS_SKILL" ]]; then log_fail "File not found"; return; fi
    local lines
    lines=$(wc -l < "$UPDATING_DOCS_SKILL" | tr -d ' ')
    if [[ "$lines" -le 500 ]]; then
        log_pass
    else
        log_fail "SKILL.md has $lines lines (max 500)"
    fi
}

# derived_from: dimension:boundary (dispatch budget: scaffold=5, incremental=3)
# Anticipate: If the budget numbers change, agent concurrency could exceed
# limits or under-utilize available slots.
test_skill_documents_dispatch_budgets() {
    log_test "updating-docs/SKILL.md documents dispatch budgets (scaffold=5, incremental=3)"

    if [[ ! -f "$UPDATING_DOCS_SKILL" ]]; then log_fail "File not found"; return; fi
    local has_scaffold has_incremental
    has_scaffold=$(grep -c 'max 5 dispatches' "$UPDATING_DOCS_SKILL" || true)
    has_incremental=$(grep -c 'max 3 dispatches' "$UPDATING_DOCS_SKILL" || true)
    if [[ "$has_scaffold" -ge 1 ]] && [[ "$has_incremental" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing dispatch budget docs (scaffold:$has_scaffold, incremental:$has_incremental)"
    fi
}

# derived_from: dimension:boundary (writer supersede match requires min 3 words)
# Anticipate: If the 3-word minimum is deleted, short titles like
# "Auth" could false-match against many ADRs.
test_writer_supersede_requires_three_words() {
    log_test "documentation-writer supersede matching requires min 3 words"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '3 whitespace-delimited words\|at least 3.*words' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing 3-word minimum for supersede matching"
    fi
}


# ============================================================
# Dimension 3: Adversarial / Negative Testing
# ============================================================

# derived_from: dimension:adversarial (SYNC markers present in all enriched-doc files)
# Anticipate: If a SYNC marker is deleted from one file but remains in others,
# the synchronized sections would drift apart during edits.
test_sync_markers_present_in_all_enriched_files() {
    log_test "SYNC markers present in skill, finish-feature, wrap-up, and generate-docs"

    local missing=0
    grep -q '<!-- SYNC: enriched-doc-dispatch -->' "$UPDATING_DOCS_SKILL" || ((missing++)) || true
    grep -q '<!-- SYNC: enriched-doc-dispatch -->' "$FINISH_FEATURE_CMD" || ((missing++)) || true
    grep -q '<!-- SYNC: enriched-doc-dispatch -->' "$WRAP_UP_CMD" || ((missing++)) || true
    grep -q '<!-- SYNC: enriched-doc-dispatch -->' "$GENERATE_DOCS_CMD" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing files missing enriched-doc-dispatch SYNC markers"
    fi
}

# derived_from: dimension:adversarial (tier-resolution SYNC marker in all 3 commands)
test_tier_resolution_sync_in_commands() {
    log_test "tier-resolution SYNC marker present in finish-feature, wrap-up, generate-docs"

    local missing=0
    grep -q '<!-- SYNC: tier-resolution -->' "$FINISH_FEATURE_CMD" || ((missing++)) || true
    grep -q '<!-- SYNC: tier-resolution -->' "$WRAP_UP_CMD" || ((missing++)) || true
    grep -q '<!-- SYNC: tier-resolution -->' "$GENERATE_DOCS_CMD" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing commands missing tier-resolution SYNC marker"
    fi
}

# derived_from: dimension:adversarial (readme-changelog-dispatch SYNC in finish and wrap-up)
test_readme_changelog_sync_in_commands() {
    log_test "readme-changelog-dispatch SYNC marker in finish-feature and wrap-up"

    local missing=0
    grep -q '<!-- SYNC: readme-changelog-dispatch -->' "$FINISH_FEATURE_CMD" || ((missing++)) || true
    grep -q '<!-- SYNC: readme-changelog-dispatch -->' "$WRAP_UP_CMD" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing commands missing readme-changelog-dispatch SYNC marker"
    fi
}

# derived_from: dimension:adversarial (writer error handling for malformed researcher JSON)
# Anticipate: Without error handling, a malformed researcher JSON would crash
# the writer agent entirely instead of degrading gracefully.
test_writer_handles_malformed_researcher_json() {
    log_test "documentation-writer documents malformed researcher JSON handling"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'malformed\|best-effort\|Malformed researcher JSON' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing malformed researcher JSON handling"
    fi
}

# derived_from: dimension:adversarial (writer skip-no-markers action for files without markers)
# Anticipate: Without this guard, manually written docs would be overwritten
# by auto-generation.
test_writer_has_skip_no_markers_action() {
    log_test "documentation-writer defines skip-no-markers action value"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'skip-no-markers' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing skip-no-markers action value"
    fi
}

# derived_from: dimension:adversarial (writer skip-tier-disabled action for opt-out)
test_writer_has_skip_tier_disabled_action() {
    log_test "documentation-writer defines skip-tier-disabled action value"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'skip-tier-disabled' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing skip-tier-disabled action value"
    fi
}

# derived_from: dimension:adversarial (generate-docs handles no valid tiers gracefully)
# Anticipate: If the empty-tier guard is missing, the command would invoke
# the updating-docs skill with no tiers, causing undefined behavior.
test_generate_docs_handles_no_valid_tiers() {
    log_test "generate-docs.md documents stop on no valid tiers"

    if [[ ! -f "$GENERATE_DOCS_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'No valid documentation tiers\|Stop execution' "$GENERATE_DOCS_CMD"; then
        log_pass
    else
        log_fail "Missing no-valid-tiers error handling"
    fi
}

# derived_from: dimension:adversarial (wrap-up mode is always incremental)
# Anticipate: If wrap-up allowed scaffold mode, it could create
# unwanted tier directories during a quick wrap-up flow.
test_wrap_up_is_always_incremental() {
    log_test "wrap-up.md mode is always incremental (no scaffold)"

    if [[ ! -f "$WRAP_UP_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Mode is always.*incremental\|always `incremental`' "$WRAP_UP_CMD"; then
        log_pass
    else
        log_fail "wrap-up.md does not enforce incremental-only mode"
    fi
}


# ============================================================
# Dimension 4: Error Propagation & Failure Modes
# ============================================================

# derived_from: design:error-contract (researcher explicitly says READ ONLY: Never use Write, Edit, or Bash)
# Anticipate: Removing the explicit constraint text would weaken the
# agent's understanding of its read-only contract.
test_researcher_has_read_only_constraint_text() {
    log_test "documentation-researcher has explicit READ ONLY constraint"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'READ ONLY' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing explicit READ ONLY constraint text"
    fi
}

# derived_from: design:error-contract (researcher never runs git commands)
test_researcher_does_not_run_git() {
    log_test "documentation-researcher documents no git commands constraint"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'Never run git\|never run git' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing no-git-commands constraint"
    fi
}

# derived_from: design:error-contract (writer documents error handling section)
test_writer_has_error_handling_section() {
    log_test "documentation-writer has Error Handling section"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '## Error Handling' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing Error Handling section"
    fi
}

# derived_from: design:error-contract (generate-docs handles empty git log for timestamps)
# Anticipate: If the no-source-commits fallback is missing, an empty git log
# result would cause a bash unbound variable error.
test_generate_docs_handles_empty_git_log() {
    log_test "generate-docs.md documents no-source-commits fallback for empty git log"

    if [[ ! -f "$GENERATE_DOCS_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'no-source-commits' "$GENERATE_DOCS_CMD"; then
        log_pass
    else
        log_fail "Missing no-source-commits fallback"
    fi
}

# derived_from: design:error-contract (finish-feature has scaffold UX gate to prevent accidental scaffolding)
test_finish_feature_has_scaffold_ux_gate() {
    log_test "finish-feature.md has Scaffold UX Gate section"

    if [[ ! -f "$FINISH_FEATURE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Scaffold UX Gate\|scaffold.*gate' "$FINISH_FEATURE_CMD"; then
        log_pass
    else
        log_fail "Missing Scaffold UX Gate section"
    fi
}

# derived_from: design:error-contract (finish-feature YOLO auto-selects Skip for scaffold)
# Anticipate: If YOLO override doesn't skip scaffolding, YOLO mode could
# create unwanted directories during autonomous finish.
test_finish_feature_yolo_skips_scaffold() {
    log_test "finish-feature.md YOLO auto-selects Skip for scaffold"

    if [[ ! -f "$FINISH_FEATURE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'auto-select.*Skip\|auto.*Skip.*scaffold\|Auto-select.*Skip' "$FINISH_FEATURE_CMD"; then
        log_pass
    else
        log_fail "Missing YOLO auto-skip for scaffold"
    fi
}

# derived_from: design:error-contract (wrap-up graceful degradation when zero tier dirs exist)
test_wrap_up_has_graceful_degradation() {
    log_test "wrap-up.md documents graceful degradation for zero tier directories"

    if [[ ! -f "$WRAP_UP_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -qi 'graceful degradation\|zero tier directories\|all tiers missing' "$WRAP_UP_CMD"; then
        log_pass
    else
        log_fail "Missing graceful degradation for zero tier dirs"
    fi
}


# ============================================================
# Dimension 5: Mutation Mindset (behavioral pinning)
# ============================================================

# derived_from: dimension:mutation-line-deletion (doc_tiers line in session-start.sh exists)
# Verify: If the line reading doc_tiers is deleted from session-start.sh,
# no doc_tiers value would be injected.
test_session_start_has_doc_tiers_code_line() {
    log_test "session-start.sh has code line reading doc_tiers field"

    if grep -q 'doc_tiers' "${HOOKS_DIR}/session-start.sh"; then
        log_pass
    else
        log_fail "session-start.sh missing doc_tiers field read"
    fi
}

# derived_from: dimension:mutation-line-deletion (doc_tiers output line uses pd_ prefix)
# Verify: If the output prefix changes from pd_doc_tiers to something else,
# downstream commands reading the session context would not find it.
test_session_start_doc_tiers_has_pd_prefix() {
    log_test "session-start.sh outputs doc_tiers with pd_ prefix"

    if grep -q 'pd_doc_tiers' "${HOOKS_DIR}/session-start.sh"; then
        log_pass
    else
        log_fail "session-start.sh missing pd_doc_tiers output"
    fi
}

# derived_from: dimension:mutation-logic-inversion (researcher critical rule: drift overrides no-update)
# Verify: If the logic is inverted (drift -> no_updates_needed=true instead of false),
# drifted documentation would never be updated.
test_researcher_drift_overrides_no_update() {
    log_test "documentation-researcher documents drift-overrides-no-update critical rule"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Critical Rule.*Drift\|Drift.*Override.*No-Update\|no_updates_needed.*MUST be.*false' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing drift-overrides-no-update critical rule"
    fi
}

# derived_from: dimension:mutation-boundary-shift (writer both START formats documented)
# Verify: If only one format is documented, legacy markers would not be detected.
test_writer_accepts_both_marker_formats() {
    log_test "documentation-writer accepts both marker formats (simple and annotated)"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Check both legacy/simple and annotated format documented
    if grep -q 'AUTO-GENERATED: START -->' "$WRITER_AGENT" && grep -q 'AUTO-GENERATED: START - source:' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing one of the two marker format specifications"
    fi
}

# derived_from: dimension:mutation-return-value (writer action values table is complete)
# Verify: If an action value is removed from the table, the output format
# would have undocumented action strings.
test_writer_has_all_six_action_values() {
    log_test "documentation-writer defines all 6 action values"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    local missing=0
    for action in "scaffold" "update" "skip-no-markers" "skip-tier-disabled" "create-adr" "supersede-adr"; do
        grep -q "$action" "$WRITER_AGENT" || ((missing++)) || true
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 6 action values"
    fi
}

# derived_from: dimension:mutation-line-deletion (researcher mode-aware behavior documents both modes)
# Verify: Deleting one mode's documentation would leave the agent without
# guidance for that mode.
test_researcher_documents_both_modes() {
    log_test "documentation-researcher documents both scaffold and incremental modes"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '\*\*scaffold\*\*' "$RESEARCHER_AGENT" && grep -q '\*\*incremental\*\*' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing one of scaffold/incremental mode documentation"
    fi
}

# derived_from: dimension:mutation-line-deletion (doc-schema project types lists all 4 types)
# Verify: Deleting a project type would mean that type's additional files
# would not be generated during scaffold.
test_doc_schema_has_four_project_types() {
    log_test "doc-schema.md Project-Type Additions lists all 4 project types"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    local missing=0
    grep -q 'Plugin' "$DOC_SCHEMA" || ((missing++)) || true
    grep -q 'CLI' "$DOC_SCHEMA" || ((missing++)) || true
    grep -q 'API' "$DOC_SCHEMA" || ((missing++)) || true
    grep -q 'General' "$DOC_SCHEMA" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 4 project types"
    fi
}

# derived_from: dimension:mutation-arithmetic-swap (generate-docs ADR scan caps at 10 files)
# Verify: If the cap number changes or is removed, excessive design.md files
# could bloat the context.
test_generate_docs_adr_scan_cap_at_10() {
    log_test "generate-docs.md ADR scan caps at 10 most recent files"

    if [[ ! -f "$GENERATE_DOCS_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q '10' "$GENERATE_DOCS_CMD" && grep -qi 'cap\|most recent\|Cap at' "$GENERATE_DOCS_CMD"; then
        log_pass
    else
        log_fail "Missing ADR scan cap at 10 documentation"
    fi
}


# ============================================================
# Dimension 6: Deepened Coverage (Phase B) — test-deepener
# ============================================================

# derived_from: spec:TD7 (finish-feature Phase 2b must NOT invoke updating-docs skill)
# Anticipate: If finish-feature delegates to updating-docs skill instead of inlining
# the dispatch, it would add an unnecessary indirection layer and diverge from TD7.
# Challenge: We grep for the skill name in the Phase 2b section specifically.
# Verify: Removing the inline dispatch and adding a skill invocation would fail this test.
test_td7_finish_feature_phase2b_no_updating_docs_skill() {
    log_test "TD7: finish-feature Phase 2b does NOT reference updating-docs skill"

    if [[ ! -f "$FINISH_FEATURE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Phase 2b section in finish-feature
    # When we search for updating-docs skill invocation within Step 2b
    local phase2b_content
    phase2b_content=$(sed -n '/### Step 2b:/,/^---$/p' "$FINISH_FEATURE_CMD")
    # Then it does NOT invoke updating-docs skill (it inlines the dispatch per TD7)
    if echo "$phase2b_content" | grep -qi 'updating-docs'; then
        log_fail "finish-feature Phase 2b references updating-docs skill (violates TD7)"
    else
        log_pass
    fi
}

# derived_from: spec:TD7 (wrap-up Phase 2b must NOT invoke updating-docs skill)
# Anticipate: Same as above — wrap-up should inline dispatch, not delegate to skill.
test_td7_wrap_up_phase2b_no_updating_docs_skill() {
    log_test "TD7: wrap-up Phase 2b does NOT reference updating-docs skill"

    if [[ ! -f "$WRAP_UP_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Phase 2b/Step 2b section in wrap-up
    local phase2b_content
    phase2b_content=$(sed -n '/### Step 2b:/,/^---$/p' "$WRAP_UP_CMD")
    # Then it does NOT invoke updating-docs skill
    if echo "$phase2b_content" | grep -qi 'updating-docs'; then
        log_fail "wrap-up Phase 2b references updating-docs skill (violates TD7)"
    else
        log_pass
    fi
}

# derived_from: spec:ADR-supersession (case-insensitive matching documented in writer)
# Anticipate: If case-insensitive is removed, "Authentication Strategy" would not
# match "authentication strategy" — causing duplicate ADRs instead of supersession.
test_adr_supersession_case_insensitive_documented() {
    log_test "documentation-writer ADR supersession specifies case-insensitive matching"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given the Supersession Matching section
    # Then it documents case-insensitive comparison
    if grep -qi 'case-insensitive' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing case-insensitive specification in supersession matching"
    fi
}

# derived_from: spec:ADR-format-detection (writer documents both heading and table formats)
# Anticipate: If only one format is documented, design.md files using the other
# format would not be correctly parsed for ADR extraction.
test_adr_format_detection_heading_and_table() {
    log_test "documentation-writer ADR extraction documents both heading and table format detection"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given the Format Detection section
    local has_table has_heading
    has_table=$(grep -c 'Table format' "$WRITER_AGENT" || true)
    has_heading=$(grep -c 'Heading format' "$WRITER_AGENT" || true)
    # Then both formats are documented
    if [[ "$has_table" -ge 1 ]] && [[ "$has_heading" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing format detection docs (table:$has_table, heading:$has_heading)"
    fi
}

# derived_from: dimension:adversarial (SYNC labels used in SKILL.md all appear in commands)
# Anticipate: If a SYNC label exists in the skill but not in a command that should
# share the synchronized section, edits to one would drift from the other.
# This is a bidirectional consistency check — not just presence, but label matching.
test_sync_labels_bidirectional_skill_to_commands() {
    log_test "SYNC labels in SKILL.md all appear in at least one command file"

    if [[ ! -f "$UPDATING_DOCS_SKILL" ]]; then log_fail "File not found"; return; fi
    # Given SYNC labels in the skill file
    local labels
    labels=$(grep -o '<!-- SYNC: [^ ]*' "$UPDATING_DOCS_SKILL" | sed 's/<!-- SYNC: //' | sort -u)
    # When we check each label against the command files
    local missing=0
    local missing_labels=""
    while IFS= read -r label; do
        local found=0
        grep -q "<!-- SYNC: $label -->" "$FINISH_FEATURE_CMD" 2>/dev/null && found=1
        grep -q "<!-- SYNC: $label -->" "$WRAP_UP_CMD" 2>/dev/null && found=1
        grep -q "<!-- SYNC: $label -->" "$GENERATE_DOCS_CMD" 2>/dev/null && found=1
        if [[ "$found" -eq 0 ]]; then
            ((missing++)) || true
            missing_labels+=" $label"
        fi
    done <<< "$labels"
    # Then all labels are found in at least one command
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "SYNC labels from SKILL.md missing in all commands:$missing_labels"
    fi
}

# derived_from: spec:affected_tiers (researcher output uses exact field name affected_tiers)
# Anticipate: If the field name is misspelled (e.g., affectedTiers, affected_tier),
# the writer dispatch would fail to read tier assignments.
# Verify: Renaming the field in the output schema would fail this test.
test_researcher_affected_tiers_exact_field_name() {
    log_test "documentation-researcher output schema uses exact field name 'affected_tiers'"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given the Output Format section
    # Then it contains the exact JSON key "affected_tiers" (quoted, in schema)
    if grep -q '"affected_tiers"' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing exact field name '\"affected_tiers\"' in output schema"
    fi
}

# derived_from: spec:researcher-output (researcher output schema includes changelog_state)
# Anticipate: If changelog_state is missing, the writer would not know whether
# CHANGELOG entries are needed, leading to missing changelog updates.
test_researcher_changelog_state_in_output_schema() {
    log_test "documentation-researcher output schema includes changelog_state field"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '"changelog_state"' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing changelog_state field in researcher output schema"
    fi
}

# derived_from: spec:researcher-output (researcher output schema includes project_type)
# Anticipate: If project_type is removed, drift detection strategy selection
# would be invisible to downstream consumers.
test_researcher_project_type_in_output_schema() {
    log_test "documentation-researcher output schema includes project_type field"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '"project_type"' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing project_type field in researcher output schema"
    fi
}

# derived_from: spec:researcher-output (researcher output schema includes no_updates_needed)
# Anticipate: Without this boolean, the evaluation gate cannot determine whether
# to prompt the user to skip documentation.
test_researcher_no_updates_needed_in_output_schema() {
    log_test "documentation-researcher output schema includes no_updates_needed field"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '"no_updates_needed"' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing no_updates_needed field in researcher output schema"
    fi
}

# derived_from: spec:writer-output (writer output schema includes updates_skipped)
# Anticipate: Without updates_skipped, there would be no record of which files
# were intentionally skipped and why.
test_writer_updates_skipped_in_output_schema() {
    log_test "documentation-writer output schema includes updates_skipped field"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q '"updates_skipped"' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing updates_skipped field in writer output schema"
    fi
}

# derived_from: dimension:mutation-arithmetic (finish-feature dispatch budget scaffold=5, incremental=3)
# Anticipate: If budget numbers in finish-feature diverge from SKILL.md, one would
# over-dispatch while the other under-dispatches. Both must agree.
# Verify: Changing 5 to 4 or 3 to 2 in finish-feature would fail this test.
test_finish_feature_dispatch_budget_matches_spec() {
    log_test "finish-feature dispatch budget documents scaffold=5 and incremental=3 max dispatches"

    if [[ ! -f "$FINISH_FEATURE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the Writer Dispatch section in finish-feature
    local has_five has_three
    has_five=$(grep -c '5 max dispatches' "$FINISH_FEATURE_CMD" || true)
    has_three=$(grep -c '3 max dispatches' "$FINISH_FEATURE_CMD" || true)
    if [[ "$has_five" -ge 1 ]] && [[ "$has_three" -ge 1 ]]; then
        log_pass
    else
        log_fail "Budget mismatch in finish-feature (5-max:$has_five, 3-max:$has_three)"
    fi
}

# derived_from: dimension:mutation-arithmetic (wrap-up dispatch budget is always 3 max)
# Anticipate: wrap-up is always incremental, so budget should be 3 max only.
# If scaffold budget (5) appears, it contradicts the incremental-only constraint.
test_wrap_up_dispatch_budget_matches_spec() {
    log_test "wrap-up dispatch budget documents 3 max dispatches (incremental only)"

    if [[ ! -f "$WRAP_UP_CMD" ]]; then log_fail "File not found"; return; fi
    local has_three
    has_three=$(grep -c '3 max dispatches' "$WRAP_UP_CMD" || true)
    if [[ "$has_three" -ge 1 ]]; then
        log_pass
    else
        log_fail "wrap-up missing '3 max dispatches' budget documentation"
    fi
}

# derived_from: spec:tier-validation (generate-docs filters to recognized tier values only)
# Anticipate: If the recognized values list is incomplete or wrong, valid tiers
# would be filtered out or invalid tiers would pass through.
# Verify: Removing "technical" from the recognized list would fail this test.
test_generate_docs_tier_filter_to_recognized_values() {
    log_test "generate-docs.md filters tiers to recognized values: user-guide, dev-guide, technical"

    if [[ ! -f "$GENERATE_DOCS_CMD" ]]; then log_fail "File not found"; return; fi
    # Given Step 1 in generate-docs
    local missing=0
    grep -q '`user-guide`' "$GENERATE_DOCS_CMD" || ((missing++)) || true
    grep -q '`dev-guide`' "$GENERATE_DOCS_CMD" || ((missing++)) || true
    grep -q '`technical`' "$GENERATE_DOCS_CMD" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 3 recognized tier names in generate-docs filter"
    fi
}

# derived_from: spec:scaffolding (doc-schema defines three tier directory paths)
# Anticipate: If a tier directory path is missing from the schema, scaffold mode
# would not know which directory to create for that tier.
test_doc_schema_three_tier_directories_documented() {
    log_test "doc-schema.md defines user-guide, dev-guide, technical as tier headings"

    if [[ ! -f "$DOC_SCHEMA" ]]; then log_fail "File not found"; return; fi
    # Given the doc-schema file
    local missing=0
    grep -q '^## user-guide$' "$DOC_SCHEMA" || ((missing++)) || true
    grep -q '^## dev-guide$' "$DOC_SCHEMA" || ((missing++)) || true
    grep -q '^## technical$' "$DOC_SCHEMA" || ((missing++)) || true
    # Then all 3 tier headings exist as exact ## headings (not sub-headings)
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 3 exact tier headings (## user-guide, ## dev-guide, ## technical)"
    fi
}

# derived_from: spec:drift-detection (researcher compares last-updated vs injected timestamp)
# Anticipate: If the comparison logic description is removed, the researcher would
# not know HOW to detect drift, only that it should.
# Verify: Deleting the comparison instruction would fail this test.
test_researcher_drift_compares_last_updated_vs_timestamp() {
    log_test "documentation-researcher drift detection compares last-updated vs tier timestamp"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given Step 2d in the researcher
    # Then it documents comparing last-updated against injected timestamp
    if grep -q 'last-updated.*<.*tier timestamp\|last-updated.*<.*injected' "$RESEARCHER_AGENT"; then
        log_pass
    else
        log_fail "Missing comparison logic between last-updated and tier timestamp"
    fi
}

# derived_from: spec:frontmatter (writer specifies ISO 8601 UTC Z suffix)
# Anticipate: Without the Z suffix specification, timestamps could be written
# with timezone offsets (+05:00) instead, breaking drift comparison.
# Verify: Removing "UTC" or "Z" from the spec would fail this test.
test_writer_iso8601_utc_z_suffix_documented() {
    log_test "documentation-writer specifies ISO 8601 with UTC Z suffix for last-updated"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given the YAML Frontmatter Handling section
    if grep -q 'UTC.*Z\|Z.*suffix\|UTC timezone suffix' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing ISO 8601 UTC Z suffix specification in writer"
    fi
}

# derived_from: spec:preservation (writer documents preservation of content outside markers)
# Anticipate: Without this rule, the writer could modify user-written content
# that exists outside section markers, causing data loss.
# Verify: Removing the preservation rule would fail this test.
test_writer_preservation_outside_markers_documented() {
    log_test "documentation-writer documents preserving content outside markers"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'outside.*markers.*preserved\|Content.*outside.*markers' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing preservation-outside-markers rule"
    fi
}

# derived_from: dimension:mutation-line-deletion (finish-feature uses correct doc-schema Glob pattern)
# Anticipate: If the Glob path changes, finish-feature would fail to find doc-schema,
# causing the enriched doc dispatch to proceed without schema context.
test_finish_feature_doc_schema_glob_pattern() {
    log_test "finish-feature uses doc-schema Glob path matching plugin portability convention"

    if [[ ! -f "$FINISH_FEATURE_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the doc-schema resolution section
    if grep -q 'plugins/cache/\*/pd\*/\*/references/doc-schema.md' "$FINISH_FEATURE_CMD"; then
        log_pass
    else
        log_fail "Missing portable doc-schema Glob pattern in finish-feature"
    fi
}

# derived_from: dimension:mutation-line-deletion (wrap-up uses same doc-schema Glob pattern as finish-feature)
# Anticipate: If wrap-up uses a different path than finish-feature, one would find
# the schema while the other would not, causing inconsistent behavior.
test_wrap_up_doc_schema_glob_pattern() {
    log_test "wrap-up uses doc-schema Glob path matching plugin portability convention"

    if [[ ! -f "$WRAP_UP_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'plugins/cache/\*/pd\*/\*/references/doc-schema.md' "$WRAP_UP_CMD"; then
        log_pass
    else
        log_fail "Missing portable doc-schema Glob pattern in wrap-up"
    fi
}

# derived_from: dimension:mutation-return-value (finish-feature documents no-source-commits fallback)
# Anticipate: If the fallback string is missing or changed, empty git log results
# would leave tier timestamps undefined instead of using a safe sentinel.
test_finish_feature_no_source_commits_fallback() {
    log_test "finish-feature documents no-source-commits fallback for empty git log"

    if [[ ! -f "$FINISH_FEATURE_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'no-source-commits' "$FINISH_FEATURE_CMD"; then
        log_pass
    else
        log_fail "Missing no-source-commits fallback in finish-feature"
    fi
}

# derived_from: dimension:mutation-return-value (wrap-up documents no-source-commits fallback)
test_wrap_up_no_source_commits_fallback() {
    log_test "wrap-up documents no-source-commits fallback for empty git log"

    if [[ ! -f "$WRAP_UP_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'no-source-commits' "$WRAP_UP_CMD"; then
        log_pass
    else
        log_fail "Missing no-source-commits fallback in wrap-up"
    fi
}

# derived_from: spec:ADR-naming (writer documents ADR slug format: lowercase, hyphens)
# Anticipate: If the slug format is not documented, ADR filenames could use
# spaces or mixed case, breaking filesystem conventions.
test_adr_slug_format_lowercase_hyphens() {
    log_test "documentation-writer ADR slug format specifies lowercase with hyphens"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    if grep -q 'lowercase.*hyphens\|lowercase.*spaces.*punctuation.*replaced.*hyphens' "$WRITER_AGENT"; then
        log_pass
    else
        log_fail "Missing lowercase/hyphens specification for ADR slug format"
    fi
}

# derived_from: spec:researcher-output (tier_drift entries have required subfields: tier, file, last_updated, latest_source_change, reason)
# Anticipate: If a required subfield is missing from the schema example, the writer
# would not receive complete drift information for remediation.
# Verify: Removing any of the 5 subfields would fail this test.
test_researcher_tier_drift_field_has_required_subfields() {
    log_test "documentation-researcher tier_drift entries have 5 required subfields"

    if [[ ! -f "$RESEARCHER_AGENT" ]]; then log_fail "File not found"; return; fi
    local missing=0
    # Check within the tier_drift array example in the output schema
    grep -q '"tier":' "$RESEARCHER_AGENT" || ((missing++)) || true
    grep -q '"file":' "$RESEARCHER_AGENT" || ((missing++)) || true
    grep -q '"last_updated":' "$RESEARCHER_AGENT" || ((missing++)) || true
    grep -q '"latest_source_change":' "$RESEARCHER_AGENT" || ((missing++)) || true
    grep -q '"reason":' "$RESEARCHER_AGENT" || ((missing++)) || true
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "Missing $missing of 5 required tier_drift subfields"
    fi
}

# derived_from: dimension:mutation-boundary-shift (create-adr and supersede-adr are distinct actions)
# Anticipate: If create-adr and supersede-adr are merged into a single action,
# the output would lose the distinction between new ADRs and supersession updates.
test_writer_create_adr_and_supersede_adr_actions_distinct() {
    log_test "documentation-writer defines create-adr and supersede-adr as separate action values"

    if [[ ! -f "$WRITER_AGENT" ]]; then log_fail "File not found"; return; fi
    # Given the Action Values table
    local create_count supersede_count
    create_count=$(grep -c '`create-adr`\|create-adr' "$WRITER_AGENT" || true)
    supersede_count=$(grep -c '`supersede-adr`\|supersede-adr' "$WRITER_AGENT" || true)
    # Then both appear and are distinct entries
    if [[ "$create_count" -ge 1 ]] && [[ "$supersede_count" -ge 1 ]]; then
        log_pass
    else
        log_fail "create-adr ($create_count) and supersede-adr ($supersede_count) not both present as distinct actions"
    fi
}

# derived_from: spec:TD7-prerequisites (SKILL.md documents that finish-feature and wrap-up do NOT invoke this skill)
# Anticipate: If this disclaimer is removed from the skill, future editors might
# incorrectly wire finish-feature/wrap-up to invoke the skill, violating TD7.
test_skill_not_invoked_by_finish_or_wrap_up() {
    log_test "updating-docs SKILL.md documents that finish-feature and wrap-up do NOT invoke this skill"

    if [[ ! -f "$UPDATING_DOCS_SKILL" ]]; then log_fail "File not found"; return; fi
    if grep -q 'do NOT invoke this skill\|they do NOT invoke this skill' "$UPDATING_DOCS_SKILL"; then
        log_pass
    else
        log_fail "Missing TD7 disclaimer in skill prerequisites"
    fi
}


# ============================================================
# Run all tests
# ============================================================
main() {
    echo "=========================================="
    echo "Enriched Documentation Phase Tests"
    echo "=========================================="
    echo ""

    echo "--- Dimension 1: BDD Scenarios (Hook) ---"
    echo ""

    test_session_start_injects_doc_tiers_default
    test_session_start_injects_custom_doc_tiers
    test_session_start_injects_single_tier
    test_session_start_doc_tiers_valid_json

    echo ""
    echo "--- Dimension 1: BDD Scenarios (doc-schema) ---"
    echo ""

    test_doc_schema_defines_three_tiers
    test_doc_schema_has_yaml_frontmatter_template
    test_doc_schema_has_section_marker_template
    test_doc_schema_has_tier_to_source_monitoring
    test_doc_schema_has_project_type_additions
    test_doc_schema_has_workflow_artifacts_index
    test_doc_schema_section_markers_use_auto_generated
    test_doc_schema_frontmatter_has_required_fields

    echo ""
    echo "--- Dimension 1: BDD Scenarios (agents/commands) ---"
    echo ""

    test_researcher_agent_is_read_only
    test_researcher_agent_has_read_tools
    test_writer_agent_has_write_tools
    test_researcher_has_three_tier_discovery
    test_researcher_has_frontmatter_drift_detection
    test_researcher_output_has_tier_fields
    test_writer_has_section_marker_handling
    test_writer_has_yaml_frontmatter_handling
    test_writer_has_adr_extraction
    test_writer_has_tier_specific_guidance
    test_generate_docs_has_frontmatter

    echo ""
    echo "--- Dimension 2: Boundary Values ---"
    echo ""

    test_doc_schema_user_guide_has_3_files
    test_doc_schema_dev_guide_has_3_files
    test_doc_schema_technical_has_4_files
    test_writer_adr_numbering_is_three_digit
    test_doc_schema_markers_are_paired
    test_updating_docs_skill_under_500_lines
    test_skill_documents_dispatch_budgets
    test_writer_supersede_requires_three_words

    echo ""
    echo "--- Dimension 3: Adversarial / Negative ---"
    echo ""

    test_sync_markers_present_in_all_enriched_files
    test_tier_resolution_sync_in_commands
    test_readme_changelog_sync_in_commands
    test_writer_handles_malformed_researcher_json
    test_writer_has_skip_no_markers_action
    test_writer_has_skip_tier_disabled_action
    test_generate_docs_handles_no_valid_tiers
    test_wrap_up_is_always_incremental

    echo ""
    echo "--- Dimension 4: Error Propagation ---"
    echo ""

    test_researcher_has_read_only_constraint_text
    test_researcher_does_not_run_git
    test_writer_has_error_handling_section
    test_generate_docs_handles_empty_git_log
    test_finish_feature_has_scaffold_ux_gate
    test_finish_feature_yolo_skips_scaffold
    test_wrap_up_has_graceful_degradation

    echo ""
    echo "--- Dimension 5: Mutation Mindset ---"
    echo ""

    test_session_start_has_doc_tiers_code_line
    test_session_start_doc_tiers_has_pd_prefix
    test_researcher_drift_overrides_no_update
    test_writer_accepts_both_marker_formats
    test_writer_has_all_six_action_values
    test_researcher_documents_both_modes
    test_doc_schema_has_four_project_types
    test_generate_docs_adr_scan_cap_at_10

    echo ""
    echo "--- Dimension 6: Deepened Coverage (Phase B) ---"
    echo ""

    test_td7_finish_feature_phase2b_no_updating_docs_skill
    test_td7_wrap_up_phase2b_no_updating_docs_skill
    test_adr_supersession_case_insensitive_documented
    test_adr_format_detection_heading_and_table
    test_sync_labels_bidirectional_skill_to_commands
    test_researcher_affected_tiers_exact_field_name
    test_researcher_changelog_state_in_output_schema
    test_researcher_project_type_in_output_schema
    test_researcher_no_updates_needed_in_output_schema
    test_writer_updates_skipped_in_output_schema
    test_finish_feature_dispatch_budget_matches_spec
    test_wrap_up_dispatch_budget_matches_spec
    test_generate_docs_tier_filter_to_recognized_values
    test_doc_schema_three_tier_directories_documented
    test_researcher_drift_compares_last_updated_vs_timestamp
    test_writer_iso8601_utc_z_suffix_documented
    test_writer_preservation_outside_markers_documented
    test_finish_feature_doc_schema_glob_pattern
    test_wrap_up_doc_schema_glob_pattern
    test_finish_feature_no_source_commits_fallback
    test_wrap_up_no_source_commits_fallback
    test_adr_slug_format_lowercase_hyphens
    test_researcher_tier_drift_field_has_required_subfields
    test_writer_create_adr_and_supersede_adr_actions_distinct
    test_skill_not_invoked_by_finish_or_wrap_up

    echo ""
    echo "=========================================="
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed"
    if [[ $TESTS_SKIPPED -gt 0 ]]; then
        echo "Skipped: ${TESTS_SKIPPED}"
    fi
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
